import pandas as pd
import numpy as np

from cod_prep.claude.cod_process import CodProcess
from cod_prep.downloaders.causes import get_parent_and_childen_causes
from cod_prep.downloaders.locations import (
    get_country_level_location_id, add_location_metadata
)
from cod_prep.downloaders.ages import add_age_metadata
from cod_prep.claude.configurator import Configurator

pd.options.mode.chained_assignment = None

CONF = Configurator('standard')
N_DRAWS = CONF.get_resource('uncertainty_draws')


class RTIAdjuster(CodProcess):

    death_cols = ['deaths', 'deaths_corr', 'deaths_raw', 'deaths_rd']
    rti_sources = ['Various_RTI', 'GSRRS_Bloomberg_RTI']

    def __init__(self, df, cause_meta_df, age_meta_df, location_meta_df):
        self.df = df
        self.merge_cols = ['simple_age', 'iso3', 'year_id', 'sex_id']
        self.orig_cols = df.columns
        self.cmdf = cause_meta_df
        self.amdf = age_meta_df
        self.lmdf = location_meta_df

    def get_computed_dataframe(self):
        inj_trans_causes = list(self.cmdf[
            self.cmdf.acause.str.startswith('inj_trans')
        ].cause_id.unique())
        df = self.df[self.df.cause_id.isin(inj_trans_causes)]
        # remake cf proportion
        df = df.groupby(['location_id', 'year_id',
                         'sex_id', 'age_group_id',
                         'nid', 'extract_type_id']).apply(self.cf_without_cc_code)
        df = self.apply_rti_fractions(df)
        df = self.cleanup(df)
        self.diag_df = df.copy()
        return df

    def cf_without_cc_code(self, df):
        df['cf'] = df['cf'] / df.cf.sum()
        return df

    def apply_rti_fractions(self, df):
        df, rti_fraction_input = self.prep_df_and_rti_fractions(df, self.amdf, self.lmdf)
        df = df.merge(rti_fraction_input, how='left', on=self.merge_cols)
        df['cf'] = df['new_cf'] * df['rti_fraction']
        return df

    def cleanup(self, df):
        df = df.drop(['simple_age', 'iso3', 'rti_fraction'], axis=1)
        return df

    def prep_rti_fractions(self, df, age_meta_df, location_meta_df):
        # modify df
        df = add_age_metadata(df, 'simple_age', age_meta_df=age_meta_df)
        df = add_location_metadata(df, 'ihme_loc_id', location_meta_df=location_meta_df)
        df['iso3'] = df['ihme_loc_id'][:3]
        df = df.drop('ihme_loc_id', axis=1)

        rti_fractions = CONF.get_resource("RTI_fractions")
        rti_fractions = pd.read_stata(rti_fractions)
        rti_fractions = rti_fractions.rename(columns={'age': 'simple_age',
                                                      'year': 'year_id',
                                                      'sex': 'sex_id'})
        twenty_eleven = rti_fractions[rti_fractions.year_id == 2011]
        twenty_eleven['year_id'] = 2012
        rti_fractions = rti_fractions.append(twenty_eleven, ignore_index=True)
        return df, rti_fractions

    def get_diagnostic_dataframe(self):
        try:
            return self.diag_df
        except AttributeError:
            print(
                "You requested the diag dataframe before it was ready, "
                "returning an empty dataframe."
            )
        return pd.DataFrame()


class MaternalHIVRemover(CodProcess):

    death_cols = ['deaths', 'deaths_corr', 'deaths_raw', 'deaths_rd']

    def __init__(self, df, env_meta_df, env_hiv_meta_df, source, nid):
        self.df = df
        self.maternal_env_sources = CONF.get_resource('maternal_env_sources')
        self.maternal_ages = range(7, 16)
        self.env_meta_df = env_meta_df
        self.env_hiv_meta_df = env_hiv_meta_df
        self.merge_cols = ['age_group_id', 'location_id', 'year_id', 'sex_id']
        self.orig_cols = df.columns
        self.source = source
        self.nid = nid
        self.maternal_cause_id = 366
        self.cc_code = 919

    def get_computed_dataframe(self):
        """Compute that dataframe."""
        df = self.flag_observations_to_adjust()
        env_df = self.calculate_hiv_envelope_ratio()
        df = self.adjust_deaths(df, env_df)

        # optional diagnostics
        self.diag_df = df.copy()

        # clean up final and process columns
        df = self.cleanup(df)
        return df

    def get_diagnostic_dataframe(self):
        """Return diagnostics."""
        try:
            return self.diag_df
        except AttributeError:
            print(
                "You requested the diag dataframe before it was ready, "
                "returning an empty dataframe."
            )
            return pd.DataFrame()

    def flag_observations_to_adjust(self):
        df = self.df.copy()
        try:
            nid_df = pd.read_excel(
                self.maternal_env_sources.format(source=self.source)
            )
            if self.nid in nid_df.NID.unique():
                df['used_env'] = 1
            else:
                df['used_env'] = 0
        except IOError:
            df['used_env'] = 0

        if self.maternal_cause_id in df.cause_id.unique():
            df.loc[
                (df['used_env'] == 0) & (df['sex_id'] == 2) &
                (df['cause_id'] == self.cc_code) &
                (df['age_group_id'].isin(self.maternal_ages)), 'adjust'
            ] = 1
            df['adjust'] = df['adjust'].fillna(0)
        else:
            df['adjust'] = 0

        return df

    def calculate_hiv_envelope_ratio(self):
        self.env_hiv_meta_df.rename(
            columns={'mean_env': 'mean_hiv_env'}, inplace=True
        )
        env_df = self.env_hiv_meta_df.merge(
            self.env_meta_df, on=self.merge_cols
        )
        env_df['hiv_ratio'] = env_df['mean_env'] / env_df['mean_hiv_env']
        env_df.drop(['lower_x', 'upper_x', 'lower_y',
                     'upper_y', 'run_id_x', 'run_id_y'], axis=1, inplace=True)

        assert (
            (env_df['hiv_ratio'] <= 1.001) & (env_df['hiv_ratio'] > 0)
        ).values.all(), "HIV envelope ratio must be between 1 and 0"

        return env_df

    def adjust_deaths(self, df, env_df):
        df = df.merge(env_df, on=self.merge_cols, how='left')

        df.loc[df['hiv_ratio'] < .05, 'hiv_ratio'] = .05

        for col in self.death_cols:
            df[col + '_adj'] = df[col].copy()
            df.loc[
                df['adjust'] == 1, col + '_adj'
            ] = df['hiv_ratio'] * df[col + '_adj']

        return df

    def cleanup(self, df):
        for col in self.death_cols:
            df[col] = df[col + '_adj'].copy()
        df = df[self.orig_cols]
        return df


class SampleSizeCauseRemover(CodProcess):

    adjust_causes = [298, 729, 945]
    cf_cols = ['cf', 'cf_rd', 'cf_corr', 'cf_raw']

    def __init__(self, cause_meta_df):
        self.cause_meta_df = cause_meta_df
        self.sample_size_cols = ['location_id', 'year_id', 'sex_id',
                                 'site_id', 'nid', 'extract_type_id',
                                 'age_group_id']
        self.affected_causes = get_parent_and_childen_causes(
            self.adjust_causes, self.cause_meta_df)

    def get_computed_dataframe(self, df):
        df = self.set_adjustment_causes(df)
        df = self.set_affected_causes(df)
        df = self.adjust_sample_size(df)
        df = self.remake_cf(df)
        self.diag_df = df.copy()
        df = self.cleanup(df)
        return df

    def get_diagnostic_dataframe(self):
        try:
            return self.diag_df
        except AttributeError:
            print(
                "You requested the diag dataframe before it was ready, "
                "returning an empty dataframe."
            )
            return pd.DataFrame()

    def set_adjustment_causes(self, df):
        df = df.copy()
        df['is_adjustment_cause'] = 0
        is_adjustment_cause = df['cause_id'].isin(self.adjust_causes)
        df.loc[is_adjustment_cause, "is_adjustment_cause"] = 1
        return df

    def set_affected_causes(self, df):
        df = df.copy()
        df['is_affected_cause'] = 0
        df.loc[
            df['cause_id'].isin(self.affected_causes),
            "is_affected_cause"
        ] = 1
        return df

    def adjust_sample_size(self, df):
        df = df.copy()
        is_adjust_cause = df['is_adjustment_cause'] == 1
        df.loc[is_adjust_cause, 'deaths_remove'] = df['cf'] * df['sample_size']
        df['deaths_remove'] = df['deaths_remove'].fillna(0)

        df['sample_size_remove'] = df.groupby(
            self.sample_size_cols, as_index=False
        )['deaths_remove'].transform('sum')

        df['sample_size_adj'] = df['sample_size']
        is_affected_cause = df['is_affected_cause'] == 1
        df.loc[
            ~is_affected_cause,
            'sample_size_adj'
        ] = df['sample_size_adj'] - df['sample_size_remove']

        return df

    def remake_cf(self, df):
        df = df.copy()
        for cf_col in self.cf_cols:
            df[cf_col] = (df[cf_col] * df['sample_size']) / \
                df['sample_size_adj']
            df[cf_col] = df[cf_col].fillna(0)
        df['deaths'] = df['sample_size_adj'] * df['cf']
        return df

    def cleanup(self, df):
        df = df.copy()
        df = df.drop(
            ['is_affected_cause', 'is_adjustment_cause', 'sample_size',
             'deaths_remove', 'sample_size_remove'],
            axis=1
        )
        df.rename(columns={'sample_size_adj': 'sample_size'}, inplace=True)
        return df


class Raker(CodProcess):

    def __init__(self, df, source):
        self.df = df
        self.source = source
        self.merge_cols = ['sex_id', 'age_group_id',
                           'cause_id', 'year_id', 'iso3']
        self.cf_cols = ['cf_final']
        self.draw_cols = [x for x in self.df.columns if 'cf_draw_' in x]
        if len(self.draw_cols) > 0:
            self.cf_cols = self.draw_cols + ['cf_final']
        self.death_cols = ['deaths' + x.split('cf')[1] for x in self.cf_cols]

    def get_computed_dataframe(self, location_hierarchy):
        start = len(self.df)

        df = self.add_iso3(self.df, location_hierarchy)
        df = self.flag_aggregates(df, location_hierarchy)
        if 0 in df['is_nat'].unique():

            df = self.make_deaths(df)

            aggregate_df = self.prep_aggregate_df(df)
            subnational_df = self.prep_subnational_df(df)
            sub_and_agg = subnational_df.merge(
                aggregate_df, on=self.merge_cols, how='left'
            )
            for death_col in self.death_cols:
                sub_and_agg.loc[
                    sub_and_agg['{}_agg'.format(death_col)].isnull(),
                    '{}_agg'.format(death_col)
                ] = sub_and_agg['{}_sub'.format(death_col)]
            sub_and_agg.loc[
                sub_and_agg['sample_size_agg'].isnull(), 'sample_size_agg'
            ] = sub_and_agg['sample_size_sub']
            df = df.merge(sub_and_agg, how='left', on=self.merge_cols)

            end = len(df)
            assert start == end, "The number of rows have changed,"\
                                 " this really shouldn't happen."
            df = self.replace_metrics(df)
            df = self.cleanup(df)
        else:
            df = df.drop('is_nat', axis=1)
        return df

    def cleanup(self, df):
        sub_cols = [x for x in df.columns if 'sub' in x]
        agg_cols = [x for x in df.columns if 'agg' in x]
        prop_cols = [x for x in df.columns if 'prop' in x]
        df = df.drop(sub_cols + agg_cols + prop_cols +
                     self.death_cols + ['is_nat'], axis=1)
        return df

    def add_iso3(self, df, location_hierarchy):
        df = add_location_metadata(df, 'ihme_loc_id',
                                   location_meta_df=location_hierarchy)
        df['iso3'] = df['ihme_loc_id'].str[0:3]
        df.drop(['ihme_loc_id'], axis=1, inplace=True)
        return df

    def prep_subnational_df(self, df):
        df = df[df['is_nat'] == 0]
        sub_total = df.groupby(
            self.merge_cols, as_index=False
        )[self.death_cols + ['sample_size']].sum()

        # create _sub columns
        for death_col in self.death_cols:
            sub_total.loc[sub_total[death_col] == 0, death_col] = .0001
            sub_total.rename(
                columns={death_col: death_col + '_sub'}, inplace=True
            )
        sub_total.rename(columns={'sample_size': 'sample_size_sub'}, inplace=True)

        sub_total = sub_total[
            self.merge_cols + [x for x in sub_total.columns if 'sub' in x]
        ]

        return sub_total

    def flag_aggregates(self, df, location_hierarchy):
        country_locations = get_country_level_location_id(
            df.location_id.unique(), location_hierarchy)
        df = df.merge(country_locations, how='left', on='location_id')
        df.loc[df['location_id'] == df['country_location_id'], 'is_nat'] = 1
        df.loc[df['location_id'] != df['country_location_id'], 'is_nat'] = 0
        df = df.drop('country_location_id', axis=1)
        return df

    def replace_metrics(self, df):
        if self.source == "Other_Maternal":
            df['prop_ss'] = df['sample_size_agg'] / df['sample_size_sub']
            df.loc[
                df['is_nat'] == 0, 'sample_size'
            ] = df['sample_size'] * df['prop_ss']

        for death_col in self.death_cols:

            df['{}_prop'.format(death_col)] = \
                df['{}_agg'.format(death_col)] / df['{}_sub'.format(death_col)]
            df.loc[df['is_nat'] == 0, death_col] = \
                df[death_col] * df['{}_prop'.format(death_col)]

            cf_col = 'cf' + death_col.split('deaths')[1]
            df.loc[df['is_nat'] == 0, cf_col] = df[death_col] / df['sample_size']
            df.loc[df[cf_col] > 1, cf_col] = 1

        return df

    def prep_aggregate_df(self, df):
        df = df[df['is_nat'] == 1]

        for death_col in self.death_cols:
            df = df.rename(columns={death_col: death_col + '_agg'})

        df = df.rename(columns={'sample_size': 'sample_size_agg'})

        df = df[
            self.merge_cols + [x for x in df.columns if '_agg' in x]
        ]
        df = df.groupby(self.merge_cols, as_index=False).sum()

        return df

    def make_deaths(self, df):
        for cf_col in self.cf_cols:
            df['deaths' + cf_col.split('cf')[1]] = df[cf_col] * df['sample_size']
        return df


class AnemiaAdjuster(CodProcess):

    cf_cols = ['cf', 'cf_raw', 'cf_corr', 'cf_rd']
    anemia_cause_id = 390

    def __init__(self):
        self.anemia_props_path = CONF.get_resource('va_anemia_proportions')
        self.location_set_version_id = CONF.get_id('location_set_version')

    def get_computed_dataframe(self, df):
        original_columns = list(df.columns)

        orig_deaths_sum = (df['cf'] * df['sample_size']).sum()

        anemia_props = pd.read_csv(self.anemia_props_path)
        anemia_df = df.loc[df['cause_id'] == self.anemia_cause_id]
        anemia_df = add_location_metadata(
            anemia_df, 'ihme_loc_id',
            location_set_version_id=self.location_set_version_id,
            force_rerun=False
        )
        anemia_df['iso3'] = anemia_df['ihme_loc_id'].str.slice(0, 3)
        unique_iso3s = list(anemia_df['iso3'].unique())
        merge_props = anemia_props.loc[
            anemia_props['iso3'].isin(unique_iso3s)
        ]
        unique_years = list(anemia_df.year_id.unique())
        years_under_90 = [u for u in unique_years if u < 1990]
        if len(years_under_90) > 0:
            props_90 = merge_props.query('year_id == 1990')
            for copy_year in years_under_90:
                copy_props = props_90.copy()
                copy_props['year_id'] = copy_year
                merge_props = merge_props.append(
                    copy_props, ignore_index=True)
        anemia_df = anemia_df.merge(
            merge_props,
            on=['iso3', 'year_id', 'age_group_id', 'sex_id', 'cause_id'],
            how='left'
        )
        self.diag_df = anemia_df

        sum_to_one_id_cols = list(set(original_columns) - set(self.cf_cols))
        assert np.allclose(
            anemia_df.groupby(
                sum_to_one_id_cols
            )['anemia_prop'].sum(),
            1
        )

        anemia_df['cause_id'] = anemia_df['target_cause_id']
        for cf_col in self.cf_cols:
            anemia_df[cf_col] = anemia_df[cf_col] * anemia_df['anemia_prop']

        anemia_df = anemia_df[original_columns]

        df = df.loc[df['cause_id'] != self.anemia_cause_id]
        df = df.append(anemia_df, ignore_index=True)

        sum_cols = self.cf_cols
        group_cols = list(set(df.columns) - set(sum_cols))
        df = df.groupby(group_cols, as_index=False)[sum_cols].sum()

        new_deaths_sum = (df['cf'] * df['sample_size']).sum()

        assert np.allclose(orig_deaths_sum, new_deaths_sum)

        return df

    def get_diagnostic_dataframe(self):
        if self.diag_df is not None:
            return self.diag_df
        else:
            print("Run get computed dataframe first")
