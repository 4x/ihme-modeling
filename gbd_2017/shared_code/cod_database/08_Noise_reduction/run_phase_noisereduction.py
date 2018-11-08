"""Noise reduction phase."""
import sys
import os
import pandas as pd

this_dir = os.path.dirname(os.path.abspath(__file__))
repo_dir = os.path.abspath(os.path.join(this_dir, '../..'))
sys.path.append(repo_dir)

from cod_prep.claude.noise_reduction import NoiseReducer
from cod_prep.claude.configurator import Configurator
from cod_prep.downloaders import (
    get_value_from_nid,
    get_datasets,
    get_malaria_model_group_from_nid
)

from cod_prep.utils import print_log_message, just_keep_trying, report_duplicates
from cod_prep.claude.claude_io import write_phase_output, get_claude_data
from cod_prep.claude.run_phase_nrmodel import model_group_is_run_by_cause
pd.options.mode.chained_assignment = None


CONF = Configurator('standard')
# sources containing maternal deaths that are noise reduced
MATERNAL_NR_SOURCES = [
    "Mexico_BIRMM", "Maternal_report", "SUSENAS",
    "China_MMS_1996_2005", "China_MMS_2006_2012", "China_Child_1996_2012"
]

NR_DIR = CONF.get_directory('nr_process_data')


def get_malaria_noise_reduction_model_result(malaria_model_group, launch_set_id):
    """Read in the csv with saved malaria model result."""
    malaria_dfs = []
    for model_group in malaria_model_group:
        if model_group != "NO_NR":
            malaria_filepath = "FILEPATH".format(
                nr=NR_DIR, model_group=model_group, lsid=launch_set_id)
            df = just_keep_trying(
                pd.read_csv,
                args=[malaria_filepath],
                max_tries=100,
                seconds_between_tries=6,
                verbose=True
            )
            malaria_dfs.append(df)
    malaria_results = pd.concat(malaria_dfs)
    return malaria_results


def get_noise_reduction_model_result(nid, extract_type_id, launch_set_id,
                                     model_group, malaria_model_group, cause_id=None):
    """Read in the csv with saved model results."""

    if cause_id is None:
        filepath = "FILEPATH".format(
            nr=NR_DIR, model_group=model_group, lsid=launch_set_id
        )
    else:
        filepath = "FILEPATH".format(
            nr=NR_DIR, model_group=model_group, cause_id=cause_id,
            lsid=launch_set_id
        )

    results = just_keep_trying(
        pd.read_csv,
        args=[filepath],
        max_tries=100,
        seconds_between_tries=6,
        verbose=True
    )

    if len(results) == 0 and cause_id is not None:
        return results

    if "NO_NR" not in malaria_model_group:
        malaria_results = get_malaria_noise_reduction_model_result(
            malaria_model_group, launch_set_id)
        # drop malaria from the non-malaria group results
        if len(malaria_results) > 0:
            malaria = results['cause_id'] == 345
            results = results.loc[~malaria]
        results = pd.concat([results, malaria_results], ignore_index=True)
        report_duplicates(results, ['nid', 'extract_type_id', 'site_id', 'cause_id',
                                    'sex_id', 'age_group_id', 'location_id', 'year_id'])

    results = results[
        (results['nid'] == nid) &
        (results['extract_type_id'] == extract_type_id)
    ]

    # drop some columns we do not need anymore
    results = results.drop(['country_id', 'subnat_id', 'is_loc_agg'], axis=1)

    if 'VA-' not in model_group:
        assert not results.isnull().values.any(), \
            "There are missing values in the {}".format(filepath)

    return results


def run_phase(nid, extract_type_id, launch_set_id, data_type_id, source,
              model_group, malaria_model_group):

    run_noise_reduction = True
    run_by_cause = False

    # determine above values using the source and model group
    if model_group == "NO_NR":
        run_noise_reduction = False

    if model_group_is_run_by_cause(model_group):
        run_by_cause = True

    if run_noise_reduction:
        if run_by_cause:

            filepath = "FILEPATH".format(
                nr=NR_DIR, model_group=model_group, lsid=launch_set_id
            )
            causes = sorted(list(pd.read_csv(filepath)['cause_id'].unique()))
            print_log_message("Reading cause-specific files".format(len(causes)))
        else:
            causes = [None]
            print_log_message("Reducing cause-appended file")

        dfs = []
        for cause_id in causes:
            df = get_noise_reduction_model_result(
                nid, extract_type_id, launch_set_id,
                model_group, malaria_model_group, cause_id=cause_id
            )
            if 'Unnamed: 0' in df.columns:
                df = df.drop('Unnamed: 0', axis=1)
            dfs.append(df)
        df = pd.concat(dfs, ignore_index=True)

        print_log_message("Running bayesian noise reduction algorithm using fitted priors")
        noise_reducer = NoiseReducer(data_type_id, source)
        df = noise_reducer.get_computed_dataframe(df)

    else:
        # simply get the aggregated result
        print_log_message(
            "Skipping noise reduction for source {} and model "
            "group {}".format(source, model_group)
        )
        df = get_claude_data(
            "aggregation", nid=nid, extract_type_id=extract_type_id
        )

    return df


def main(nid, extract_type_id, launch_set_id):

    print_log_message("Beginning noise reduction phase")

    data_type_id = get_value_from_nid(
        nid, 'data_type_id', extract_type_id=extract_type_id
    )
    source = get_value_from_nid(
        nid, 'source', extract_type_id=extract_type_id
    )
    model_group = get_value_from_nid(
        nid, 'model_group', extract_type_id=extract_type_id
    )
    malaria_model_group = get_malaria_model_group_from_nid(
        nid, extract_type_id
    )

    df = run_phase(nid, extract_type_id, launch_set_id, data_type_id,
                   source, model_group, malaria_model_group)

    print_log_message(
        "Writing {n} rows of output for launch set {ls}, nid {nid}, extract "
        "{e}".format(n=len(df), ls=launch_set_id, nid=nid, e=extract_type_id)
    )
    ids = ['age_group_id', 'cause_id', 'extract_type_id',
           'location_id', 'year_id', 'site_id', 'sex_id', 'nid']
    df[ids] = df[ids].astype(int)
    write_phase_output(df, 'noisereduction', nid,
                       extract_type_id, launch_set_id)


if __name__ == "__main__":
    nid = int(sys.argv[1])
    extract_type_id = int(sys.argv[2])
    launch_set_id = int(sys.argv[3])
    main(nid, extract_type_id, launch_set_id)
