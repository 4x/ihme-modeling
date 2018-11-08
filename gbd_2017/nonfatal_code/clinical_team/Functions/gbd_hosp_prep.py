"""
Clinical informatics functions
must run on the GBD environment or a clone
"""
import pandas as pd
import numpy as np
import platform
import getpass
import datetime
import sys
from db_queries import get_cause_metadata, get_population, get_covariate_estimates
from db_tools.ezfuncs import query
import os

if getpass.getuser() == 'USERNAME':
    sys.path.append("FILEPATH")
if getpass.getuser() == 'USERNAME':
    sys.path.append("FILEPATH")
import hosp_prep

if platform.system() == "Linux":
    root = r"FILEPATH/j"
else:
    root = "J:"


def get_sample_size(df, fix_group237=False):
    """
    This function attaches sample size to hospital data.  It's for sources that
    should have fully covered populations, so sample size is just population.
    Checks if age_group_id is a column that exists and if not, it attaches it.

    Parameters
        df: Pandas DataFrame
            contains the data that you want to add sample_size to.  Will add
            pop to every row.
    """
    # process
    ## attach age group id to data
    ## get pop with those age group ids in the data
    ## attach pop by age group id

    if 'age_group_id' not in df.columns:
        # pull age_group to age_start/age_end map
        age_group = hosp_prep.get_hospital_age_groups()

        # merge age group id on
        pre = df.shape[0]
        df = df.merge(age_group, how='left', on=['age_start', 'age_end'])
        assert df.shape[0] == pre, "number of rows changed during merge"
        assert df.age_group_id.notnull().all(), ("age_group_id is missing "
            "for some rows")

    # get population
    pop = get_population(QUERY)

    if fix_group237:

        fix_pop = get_population(QUERY)
        pre = fix_pop.shape[0]
        fix_pop['age_group_id'] = 237
        fix_pop = fix_pop.groupby(fix_pop.columns.drop('population').tolist()).agg({'population': 'sum'}).reset_index()
        assert pre/2 == fix_pop.shape[0]

        pop = pd.concat([pop, fix_pop], ignore_index=True)

    # rename pop columns to match hospital data columns
    pop.rename(columns={'year_id': 'year_start'}, inplace=True)
    pop['year_end'] = pop['year_start']
    pop.drop("run_id", axis=1, inplace=True)

    demography = ['location_id', 'year_start', 'year_end',
                  'age_group_id', 'sex_id']

    # merge on population
    pre_shape = df.shape[0]
    df = df.merge(pop, how='left', on=demography)  # attach pop info to hosp
    assert pre_shape == df.shape[0], "number of rows don't match after merge"
    assert df.population.notnull().all(),\
        "population is missing for some rows. look at this df! \n {}".\
            format(df.loc[df.population.isnull(), demography].drop_duplicates())

    return(df)



def fix_maternal_denominators(df, return_only_maternal=False):

    asfr = get_covariate_estimates(QUERY)

    # keep age/location/year and the critical mean_value
    asfr = asfr[['location_id', 'year_id', 'age_group_id', 'sex_id',
                 'mean_value']]
    asfr.drop_duplicates(inplace=True)

    # map age_start and age_end onto asfr
    age_group = query("QUERY")
    pre_asfr = asfr.shape[0]
    asfr = asfr.merge(age_group, how='left', on='age_group_id')
    assert pre_asfr == asfr.shape[0],\
    "The merge duplicated rows unexpectedly"
    asfr.drop('age_group_id', axis=1, inplace=True)
    asfr.rename(columns={'age_group_years_start': 'age_start',
                         'age_group_years_end': 'age_end'},
                inplace=True)
    # create year_start and year_end
    asfr['year_start'] = asfr['year_id']
    asfr['year_end'] = asfr['year_id']
    asfr.drop('year_id', axis=1, inplace=True)

    # all the mean_values in asfr where age_end is less than one are 0, so we
    # can make up an asfr group for age start = 0 and age_end = 1
    asfr.loc[asfr['age_end'] < 1, 'age_end'] = 1
    asfr.loc[asfr['age_start'] < 1, 'age_start'] = 0

    asfr.loc[asfr['age_end'] > 1, 'age_end'] = asfr.loc[asfr['age_end'] > 1,
             'age_end'] - 1

    # one more change, asfr has the max age end as 125 (now 124), and we want
    # it to be 99
    asfr.loc[asfr['age_end'] == 124, 'age_end'] = 99  # now asfr age_start
    # and age_end match our hospital data

    # and incase we created duplicated rows by doing this:
    asfr.drop_duplicates(inplace=True)

    # MERGE ASFR ONTO HOSP
    pre_shape = df.shape[0]
    df = df.merge(asfr, how='left', on=['age_start', 'age_end', 'year_start',
                                        'year_end', 'location_id', 'sex_id'])
    assert df.mean_value.isnull().sum() != df.shape[0],\
    "The merge failed to attach any mean_values"
    assert pre_shape == df.shape[0],\
    "The merge duplicated rows unexpectedly"

    # GET MATERNAL CAUSES
    # query causes
    causes = get_cause_metadata(QUERY)
    condition = causes.path_to_top_parent.str.contains("366")
    
    maternal_causes = causes[condition]

    # make list of maternal causes
    maternal_list = list(maternal_causes['cause_id'].unique())

    maternal_df = df[df['cause_id'].isin(maternal_list)]  # subset out rows that
    # are in maternal list
    assert maternal_df.shape[0] != 0,\
    "The maternal dataframe is empty"

    df = df[~df['cause_id'].isin(maternal_list)]  # subset out rows that
    # are not in the maternal list
    assert df.shape[0] != 0,\
    "The hospital dataframe is empty"
    for cause in maternal_list:
        
        maternal_df.loc[maternal_df['cause_id'] == cause, 'product'] =\
            maternal_df.loc[maternal_df['cause_id'] == cause, 'product'] /\
            maternal_df.loc[maternal_df['cause_id'] == cause, 'mean_value']
        maternal_df.loc[maternal_df['cause_id'] == cause, 'upper_product'] =\
            maternal_df.loc[maternal_df['cause_id'] == cause, 'upper_product'] /\
            maternal_df.loc[maternal_df['cause_id'] == cause, 'mean_value']
        maternal_df.loc[maternal_df['cause_id'] == cause, 'lower_product'] =\
            maternal_df.loc[maternal_df['cause_id'] == cause, 'lower_product'] /\
            maternal_df.loc[maternal_df['cause_id'] == cause, 'mean_value']
        # some mean_valued were zero, this is effectively an age/sex restriction
        # assign these a rate of 0
        maternal_df.loc[(maternal_df['product'].isnull()) & (maternal_df['cause_id'] == cause), ['product', 'upper_product', 'lower_product']] = 0

        # assign infinite values to 0
        maternal_df.loc[(np.isinf(maternal_df['product'])) & (maternal_df['cause_id'] == cause), ['product', 'upper_product', 'lower_product']] = 0


    if return_only_maternal == True:
        maternal_df.drop(['mean_value', 'cause_id'], axis=1, inplace=True)
        return(maternal_df)
    else:
        df = pd.concat([df, maternal_df])  # bring data back together

        # DROP ASFR info
        df.drop(['mean_value', 'cause_id'], axis=1, inplace=True)

        return(df)


def get_bundle_cause_info(df):
    # CAUSE INFORMATION
    # get cause_id so we can write to an acause
    # have to go through cause_id to get to a relationship between BID & acause
    cause_id_info = query("QUERY")
    # get acause
    acause_info = query("QUERY")
    # merge acause, bid, cause_id info together
    acause_info = acause_info.merge(cause_id_info, how="left", on="cause_id")

    # REI INFORMATION
    # get rei_id so we can write to a rei
    rei_id_info = query("QUERY")
    # get rei
    rei_info = query("QUERY")
    # merge rei, bid, rei_id together into one dataframe
    rei_info = rei_info.merge(rei_id_info, how="left", on="rei_id")

    #COMBIND REI AND ACAUSE
    # rename acause to match
    acause_info.rename(columns={'cause_id': 'cause_rei_id',
                                'acause': 'acause_rei'}, inplace=True)
    # rename rei to match
    rei_info.rename(columns={'rei_id': 'cause_rei_id',
                             'rei': 'acause_rei'}, inplace=True)

    # concat rei and acause together
    folder_info = pd.concat([acause_info, rei_info])

    # drop rows that don't have bundle_ids
    folder_info = folder_info.dropna(subset=['bundle_id'])

    # drop cause_rei_id, because we don't need it for getting data into folders
    folder_info.drop("cause_rei_id", axis=1, inplace=True)

    # drop duplicates, just in case there are any
    folder_info.drop_duplicates(inplace=True)

    # rename cause_rei
    folder_info.rename(columns={'acause_rei': 'bundle_acause_rei'},
                       inplace=True)

    # MERGE ACAUSE/REI COMBO COLUMN ONTO DATA BY BUNDLE ID
    # there are NO null acause_rei entries!
    pre = df.shape[0]
    df = df.merge(folder_info, how="left", on="bundle_id")
    assert pre == df.shape[0]

    return(df)

def help_i_lost_my_data(all_data, bundle_list, version_id, cols_to_drop=[],
                        filename="", test=True):
    """
    Function to write bundle(s) back where they belong.  Useful for when a
    modeler uses the file we gave them To upload to epi.  We they do that
    they rename columns, then forget what columns they decided to use.
    Set up to run on cluster.

    Required parameters:
    all_data: Pandas DataFrame
        dataframe that has ALL the data that you want to pull from.
        This dataframe should be completely ready for modelers.
    bundle_list: list
        list that contains the bundles you want to write somewhere.
        If you only have one, put it in a list anyways.
    version_id: string
        what version of hospital data the bundle(s) comes from.
        E.g.: "v3". Gets put into the filename.

    Optional parameters:
    cols_to_drop: list
        not every bundle needs every column.  For example, most modelers
        won't want the injuries correction factor column
        default: empty list, in which case nothing will drop
    filename: string
        default: empty string
        string that gets appended to filename.  Can be useful to help a
        modeler distinguish the new data.
    test: Boolean
        Switch that when set to True, writes data to the hospital
        folder in temp. When set to False
        writes to FILEPATH
        default: True
    """

    for bundle in bundle_list:
        
        derrick = all_data[all_data.bundle_id == bundle].copy()
        # drops cols you don't want, probably like inj cols
        derrick.drop(cols_to_drop, axis=1, inplace=True)

        # This could be done in one SQL statement, but I need two peices of
        # info anyways.
        cause_id = query("""
                         QUERY
                         """).iloc[0,1]
        acause = query("""
                       QUERY
                       """).iloc[0,1]

        date = datetime.datetime.today().strftime("%Y_%m_%d")

        if test:
            write_path = (FILEPATH)
        else:
            write_path = (FILEPATH)
        print write_path

        if not os.path.isdir(write_path):
            os.makedirs(write_path)

        save_name = "{}_{}_{}{}.xlsx".format(bundle, version_id, date, filename)

        print "Writing bundle {}".format(bundle)
        writer = pd.ExcelWriter(write_path + save_name, engine='xlsxwriter')
        derrick.to_excel(writer, sheet_name='extraction', index=False)
        writer.save()
        print "DONE with {}".format(bundle)
        print "\n"

    return

def find_mapping_diff(map_vers, id_list=[]):
    """
    Give it a list of bundle ids to see how the map changed between GBD 2015
    and GBD 2016
    """

    my_query = "QUERY"
    me_bid_map = query(my_query)
    me_bid_map.drop("modelable_entity_name", axis=1, inplace=True)
    me_bid_map.rename(columns={"bundle_name": "name"}, inplace=True)
    me_bid_map

    old_inc = pd.read_stata(r"FILEPATH")
    old_inc.drop("me_id2", axis=1, inplace=True)
    old_inc.rename(columns={'me_id1': 'modelable_entity_id'}, inplace=True)
    old_inc['measure'] = 'inc'

    old_prev = pd.read_stata(r"FILEPATH")
    old_prev.drop("me_id2", axis=1, inplace=True)
    old_prev.rename(columns={'me_id1': 'modelable_entity_id'}, inplace=True)
    old_prev['measure'] = 'prev'

    old = pd.concat([old_inc, old_prev])
    old = old[old.modelable_entity_id.isin(me_bid_map.modelable_entity_id.unique())]

    old = old.merge(me_bid_map[['modelable_entity_id', 'name']], how='left',
                    on='modelable_entity_id')

    old['icd_code'] = old.icd_code.str.replace("\W", "")

    current = pd.read_stata(r"FILEPATH".format(map_vers))
    current = current[current.bundle_id.isin(me_bid_map.bundle_id.unique())]
    current = current.merge(me_bid_map[['bundle_id', 'name']], how='left',
                            on='bundle_id')

    for me_id in me_bid_map.modelable_entity_id.unique():
        print "\n"
        bid = me_bid_map[me_bid_map.modelable_entity_id == me_id].\
            bundle_id.unique()[0]
        name = me_bid_map[me_bid_map.modelable_entity_id == me_id].\
            name.unique()[0]
        print "For me_id {}, bundle {}, {}:".format(str(me_id), bid, name)
        diff_backwards = set(current[current.bundle_id == bid].icd_code) -\
            set(old[old.modelable_entity_id == me_id].icd_code)
        print "the difference current - old is : {}".format(diff_backwards)
        diff_forwards = set(old[old.modelable_entity_id == me_id].icd_code) -\
            set(current[current.bundle_id == bid].icd_code)
        print "the difference old - current is : {}".format(diff_forwards)

def bundle_location(bundle_list):
    """
    give it a list of bundle ids, and it will return filepath for each bundle_id
    """

    file_list = []

    for bundle in bundle_list:
        cause_rei_info = query("QUERY")
        
        if cause_rei_info.size == 0:
            file_list.append("Bundle {} is not present in the database".format(int(bundle)))
            continue
        
        if cause_rei_info.rei_id.notnull().all():
            acause_rei_id = cause_rei_info.iloc[0,1]
            acause_rei_name = str(query("QUERY").iloc[0,0])
        # if this passes, we have a cause
        if cause_rei_info.cause_id.notnull().all():
            acause_rei_id = cause_rei_info.iloc[0,0]
            acause_rei_name = str(query("QUERY").iloc[0,0])
        # now we have bundle_id and acause / rei

        # so we can form the path
        writedir = (FILEPATH)

        # append path to list
        file_list.append(writedir)
    return(file_list)


def verify_missing(bundle, locs, age, sex, years,
                            map_path="FILEPATH"):
    """
    pass a clean map, a bundle and set of demographic info and the func
    will return the data if it exists and a print statement if not
    """
    if type(locs) == int:
        locs = [locs]
    if type(years) == int:
        locs = [years]
    # read in location/source map
    loc_source = pd.read_csv(r"FILEPATH")
    loc_source = loc_source[loc_source.location_id.isin(locs)]
    df_list = []
    for source in loc_source.source.unique():
        for year in years:
            try:
                df = pd.read_hdf(FILEPATH)
                df_list.append(df)
                del df
            except:
                print("couldn't read in " + source + str(year))

    data = pd.concat(df_list)
    del df_list
    amap = pd.read_csv(map_path)
    assert hosp_prep.verify_current_map(amap)
    # get the icd codes associated with a bundle
    amap = amap.query("bundle_id == @bundle")
    # subset on icd codes
    data = data[(data.cause_code.isin(amap.cause_code))]
    data = data.query("age_start == @age & sex_id == @sex")
    if data.shape[0] == 0:
        print("uuhhh, yeah. there's no data here")
        print("age {} sex {} bundle {} years {} locations {}".format(age, sex, bundle, years, locs))
    else:
        return(data)
def store_locations(df):

    loc_years = df[['year_start', 'location_id', 'source',
                    'facility_id']].drop_duplicates()

    loc_years = loc_years.merge(query("QUERY")

    locs = query("QUERY")

    loc_years = loc_years.merge(locs, how='left', on='location_id')

    locs.rename(columns={'location_id': 'location_parent_id',
                         'location_name': 'location_parent_name'}, inplace=True)

    loc_years = loc_years.merge(locs, how='left', on='location_parent_id')

    loc_years['facility_id'] = 'inpatient'

    loc_years.rename(columns={'year_start': 'year'}, inplace=True)

    # make the UTLAs have the parent of england (instead of Region)
    loc_years.loc[loc_years.path_to_top_parent.str.contains("4749"),
                  ['location_parent_id', 'location_parent_name']] = [4749,
                                                                     "England"]

    # make England have global parent (instead of United Kingdon)
    loc_years.loc[loc_years.location_id == 4749,
                  ['location_parent_id', 'location_parent_name']] = [1,
                                                                     "Global"]

    loc_years.to_excel(r"FILEPATH", index=False)

    locs = sorted(loc_years.location_name.unique())
    loc_ids = sorted(loc_years.location_id.unique())
    location_names = u"{loc}".format(loc=u", ".join(loc for loc in locs))
    location_ids = "{ids}".format(ids=', '.join(str(ids) for ids in loc_ids))
    text = open(r"FILEPATH", "w")
    text.write(location_names.encode('utf-8'))
    text.write(location_ids)
    text.close()

def all_group_id_start_end_switcher(df, remove_cols=True, ignore_nulls=False):
    """
    Takes a dataframe with age start/end OR age group ID and switches from one
    to the other

    Args:
        df: (Pandas DataFrame) data to swich age labelling
        remove_cols: (bool)  If True, will drop the column that was switched
            from
        ignore_nulls: (bool)  If True, assertions about missing ages
            will be ignored.  Not a good idea to use in production but is useful
            for when you just need to quickly see what ages you have.
    """
    
    if sum([w in ['age_start', 'age_end', 'age_group_id'] for w in df.columns]) == 3:
        print("All age columns are present, unclear which output is desired. "
        r"Simply drop the columns you don't want")
        return
    #elif 'age_start' and 'age_end' in df.columns:
    elif sum([w in ['age_start', 'age_end'] for w in df.columns]) == 2:
        merge_on = ['age_start', 'age_end']
        switch_to = ['age_group_id']

    elif 'age_group_id' in df.columns:
        merge_on = ['age_group_id']
        switch_to = ['age_start', 'age_end']
    else:
        print("Age columns not present or named incorrectly")
        return



    # pull in our hospital age groups
    ages = hosp_prep.get_hospital_age_groups()

    # determine if the data contains only our hosp age groups or not
    age_set = "hospital"
    for m in merge_on:
        ages_unique = ages[merge_on].drop_duplicates()
        df_unique = df[merge_on].drop_duplicates()
        # if their shapes aren't the same it's irregular ages
        if ages_unique.shape[0] != df_unique.shape[0]:
            age_set = 'non_hospital'
        elif (ages_unique[m].sort_values().reset_index(drop=True) != df_unique[m].sort_values().reset_index(drop=True)).all():
            age_set = 'non_hospital'

    if age_set == 'non_hospital':
        # get age info
        ages = query("QUERY")
        ages.rename(columns={"age_group_years_start": "age_start",
                                      "age_group_years_end": "age_end"},
                                      inplace=True)

        if 'age_end' in merge_on:
            # terminal age in hosp data is 99, switch to 125 so groups aren't duped
            df.loc[df['age_end'] == 100, 'age_end'] = 125
        # drop duplicates age groups that cause rows added in the merge
        duped_ages = [294, 308, 27, 161, 38, 301]
        ages = ages[~ages.age_group_id.isin(duped_ages)]

    dupes = ages[ages.duplicated(['age_start', 'age_end'], keep=False)].sort_values('age_start')

    # merge on the age group we want
    pre = df.shape[0]
    df = df.merge(ages, how='left', on=merge_on)
    assert pre == df.shape[0],\
        "Rows were duplicated, probably from these ages \n{}".format(dupes)

    # check the merge
    if not ignore_nulls:
        for s in switch_to:
            assert df[s].isnull().sum() == 0, ("{} contains missing values from "
                "the merge. The values with Nulls are {}".format(s, df.loc[df[s].isnull(), merge_on].drop_duplicates().sort_values(by=merge_on)))

    if remove_cols:
        # drop the one we don't
        df.drop(merge_on, axis=1, inplace=True)
    return(df)


def map_to_country(df):
    """
    much of our location data is subnational, but we sometimes want to tally things by country
    this function will map from any subnational location id to its parent country
    """
    pre = df.shape[0]
    cols = df.shape[1]
    # get countries from locs
    locs = get_location_metadata(location_set_id=35)
    countries = locs.loc[locs.location_type == 'admin0', ['location_id', 'location_ascii_name']].copy()
    countries.columns = ["merge_loc", "country_name"]
    # get parent ids from locs
    df = df.merge(locs[['location_id', 'path_to_top_parent']], how='left', on='location_id')
    df = pd.concat([df, df.path_to_top_parent.str.split(",", expand=True)], axis=1)
    df['merge_loc'] = df[3].astype(int)
    df = df.merge(countries, how='left', on='merge_loc')
    
    # drop all the merging cols
    df.drop(['path_to_top_parent', 0, 1, 2, 3, 4, 5, 6, 'merge_loc'], axis=1, inplace=True)
    # run a few tests
    assert df.shape[0] == pre
    assert df.shape[1] == cols + 1
    assert df.country_name.isnull().sum() == 0,\
        "Something went wrong {}".format(df[df.country_name.isnull()])
    return df
