// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************
// Purpose:		This sub-step template is for parallelized jobs submitted from main step code
// Author:		
// Last updated:	4/25/16
// Description:	Parallelization of 09_collate_outputs
// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************
// LOAD SETTINGS FROM STEP CODE (NO NEED TO EDIT THIS SECTION)

// prep stata
	clear all
	set more off
	set mem 2g
	set maxvar 32000
	if c(os) == "Unix" {
		global prefix "/home/j"
		set odbcmgr unixodbc
	}
	else if c(os) == "Windows" {
		global prefix "J:"
	}

// define locals from qsub command
	local date 			`1'
	local step_num 		`2'
	local step_name		`3'
	local code_dir 		`4'
	local in_dir 		`5'
	local out_dir 		`6'
	local tmp_dir 		`7'
	local root_tmp_dir 	`8'
	local root_j_dir 	`9'
	local cause 		`10'
	local group			`11'
	local state 		`12'

	// functional
	local functional "meningitis"
	// metric -- measure_id for prevalence(5)
	local metric 5
	// directory for standard code files
	adopath + "FILEPATH"

	// get demographics and locations
	get_location_metadata, location_set_id(9) clear
	keep if most_detailed == 1 & is_estimate == 1
	levelsof location_id, local(locations)
	clear

	get_demographics, gbd_team(epi) clear
	local years = r(year_id)
	local sexes = r(sex_id)
	clear

	// directory for pulling files from previous step
	local pull_dir_04b "FILEPATH"
	local pull_dir_05b "FILEPATH"
	local pull_dir_07 "FILEPATH"
	local pull_dir_08 "FILEPATH"
	
	// write log if running in parallel and log is not already open
	cap log using "FILEPATH", replace
	if !_rc local close 1
	else local close 0
	
// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************
// WRITE CODE HERE

	use "FILEPATH", clear
	drop if healthstate == "_parent" | grouping == "_epilepsy" | grouping == "_hearing" | grouping == "_vision"
	gen num = ""
// need to see if these files have the correct specifications
	replace num = "05b" if grouping == "long_mild" | grouping == "long_modsev"
	replace num = "07" if grouping == "cases"
	replace num = "08" if grouping == "viral"

	levelsof num if acause == "`cause'" & grouping == "`group'" & healthstate == "`state'", local(num) clean
	local n `num'

	foreach location of local locations {
		foreach year of local years {
			foreach sex of local sexes {
				use "`pull_dir_`n''/`cause'/`cause'_`state'_`location'_`year'_`sex'.dta", clear
				keep sex_id year_id age_group_id location_id measure_id draw*
				outsheet using "FILEPATH", comma replace // might need to change this for viral
				clear
			}
		}
	}

	// write check here
	file open finished using "FILEPATH", replace write
	file close finished

	if `close' log close
	clear
