// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************
// Author:		USERNAME
// Date:		DATE
// Description:	This code applies durations data to short-term incidence data to get Ecode-Ncode-platform-level prevalence of short-term injury data, the applies disability weights to get ylds
// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************
// LOAD SETTINGS FROM STEP CODE (NO NEED TO EDIT THIS SECTION)

	// prep stata
	clear all
	set more off
	set mem 2g
	set maxvar 32000
	if c(os) == "Unix" {
		global prefix "DIRECTORY"
		set odbcmgr unixodbc
	}
	else if c(os) == "Windows" {
		global prefix "DIRECTORY"
	}
	if "`1'"=="" {
		local 1 FILEPATH
		local 2 FILEPATH
		local 3 DATE
		local 4 "05a"
		local 5 scaled_short_term_en_prev_yld_by_platform
		local 6 "FILEPATH"
		local 7 114
		local 8 2005
		local 9 1
	}
	// base directory on FILEPATH
	local root_j_dir `1'
	// base directory on FILEPATH
	local root_tmp_dir `2'
	// timestamp of current run (i.e. 2014_01_17)
	local date `3'
	// step number of this step (i.e. 01a)
	local step_num `4'
	// name of current step (i.e. first_step_name)
	local step_name `5'
    // directory where the code lives
    local code_dir `6'
    // iso3
	local location_id `7'
	// year
	local year `8'
	// sex
	local sex `9'
	// directory for external inputs
	local in_dir "`root_j_dir'/FILEPATH"
	// directory for output on the FILEPATH drive
	local out_dir "`root_j_dir'/FILEPATH"
	// directory for output on FILEPATH
	local tmp_dir "`root_tmp_dir'/FILEPATH"
	// directory for standard code files
	adopath + "FILEPATH"
	
	// write log if running in parallel and log is not already open
	log using "`out_dir'/FILEPATH.smcl", replace name(worker)
	
// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************

// Filepaths
	local diag_dir "`out_dir'/FILEPATH"
	local stepfile "`code_dir'/FILEPATH.xlsx"
	local dws = "`out_dir'/FILEPATH.csv"
	local pop_file = "`out_dir'/FILEPATH.dta"
	local old_date "DATE"
// Import functions
	adopath + "`code_dir'/ado"
	
// Start timer
	start_timer, dir("`diag_dir'") name("time_`location_id'_`year'_`sex'")

// load params
	load_params

	import excel using "`code_dir'/FILEPATH.xlsx", firstrow clear
// where are the durations saved
	preserve
	keep if name == "durations"
	local this_step=step in 1
	local durations_dir = "`root_tmp_dir'/FILEPATH"
	restore
// where are the short term incidence results by EN combination saved
	keep if name == "scaled_short_term_en_inc_by_platform"
	local this_step=step in 1
	local short_term_inc_dir = "`root_tmp_dir'/FILEPATH"
		
	// Import and save durations
	import delimited using "`durations_dir'/FILEPATH.csv", delim(",") clear asdouble
	rename draw* dur_draw*
	tempfile durations
	save `durations'
	
	// Import and save disability weight draws
	import delimited "`dws'", delim(",") asdouble clear
	rename n_code ncode
	rename draw* dw*
	tempfile dws
	save `dws', replace

	// Import populations
	// Bring in pops to redistribute incidence for age groups under 1
	insheet using "`code_dir'/FILEPATH.csv", comma names clear
		tempfile age_ids 
		save `age_ids', replace
	use `pop_file', clear
		merge m:1 age_group_id using `age_ids', keep(3) assert(3) nogen
		rename age_start age 
		tostring age, replace force format(%12.3f)
		destring age, replace force
		gen collapsed_age = age
		replace collapsed_age = 0 if age < 1 
		tempfile fullpops
		save `fullpops', replace
		replace age = 0 if age < 1
		fastcollapse pop, type(sum) by(location_id year_id age sex_id)
		rename pop total_pop
		rename age collapsed_age
		tempfile pops
		save `pops', replace
	// Make pop fractions under 1
	use `fullpops', clear
		merge m:1 location_id year_id collapsed_age sex_id using `pops', keep(3) nogen
		gen pop_fraction = pop/total_pop
		keep location_id year_id age sex_id pop_fraction
		tostring age, replace force format(%12.3f)
		destring age, replace force
		tempfile pop_fractions
		save `pop_fractions', replace

local filemaker=1

	use "`short_term_inc_dir'/FILEPATH.dta", clear
		gen location_id = `location_id'
		gen year_id = `year'
		gen sex_id = `sex'
		expand 2 if age == 0, gen(dup)
		replace age = 0.01 if dup == 1
		drop dup
		expand 2 if age == 0, gen(dup)
		replace age = 0.1 if dup == 1
		drop dup
		* Redistribute collapsed 0-1 incidence to more granular age groupings
		tostring age, replace force format(%12.3f)
		destring age, replace force
		merge m:1 location_id year_id age sex_id using `pop_fractions', keep(3) nogen
		forvalues i = 0/999 {
			replace draw_`i' = draw_`i' * pop_fraction
		}

		rename draw_* inc_draw*

	* Calculate prev
		merge m:1 ncode inpatient using `durations', nogen keep(match)
	
		forvalues j=0/$drawmax {
			quietly replace inc_draw`j'=(dur_draw`j' * inc_draw`j')/( 1 + (dur_draw`j' * inc_draw`j'))
			drop dur_draw`j'
		}
		rename inc_draw* prev_draw*
		
		preserve
	* save the intermediate prevalence numbers
		rename prev_draw* draw_*
		order age, first
		sort age
		quietly format draw* %16.0g
		capture mkdir "`tmp_dir'/FILEPATH"
		if `filemaker'==1 {
			tempfile prevnums
			save `prevnums', replace
		}
		else {
			append using `prevnums'
			save `prevnums', replace
		}
		restore
		
	* Calculate YLDs	
		* Merge disability weights
		merge m:1 ncode using `dws', keep(3) nogen
		* Merge populations
		merge m:1 location_id year_id age sex_id using `fullpops', keep(3) nogen
		
		forvalues j=0/$drawmax {
			generate draw_`j'=dw`j' * (prev_draw`j' * population)
			drop dw`j' prev_draw`j'
		}
		* save YLD draws
		quietly {
			format draw* %16.0g
		}
		order age, first
		sort age
		if `filemaker'==1 {
			tempfile yldnums
			save `yldnums', replace
		}
		else {
			append using `yldnums'
			save `yldnums', replace
		}
		local ++filemaker
	** end check of existance of results for this year

** end nonshock/shock loop

use `prevnums', clear

** round up the age values
gen double true_age = round(age, 0.01)
drop age
rename true_age age
levelsof age
sort_by_ncode ncode, other_sort(inpatient age)
sort ecode

cap mkdir "`tmp_dir'/FILEPATH"
cap mkdir "`tmp_dir'/FILEPATH"
keep age draw* ecode ncode inpatient 
save "`tmp_dir'/FILEPATH.dta", replace
// save summaries
fastrowmean draw*, mean_var_name("mean")
fastpctile draw*, pct(2.5 97.5) names(ll ul)
drop draw*
order age ecode ncode inpatient mean ll ul
qui format mean ul ll %16.0g
compress
capture mkdir "`tmp_dir'/FILEPATH"
capture mkdir "`tmp_dir'/FILEPATH"
save "`tmp_dir'/FILEPATH.dta", replace

use `yldnums', clear
** round up the age values
gen double true_age = round(age, 0.01)
drop age
rename true_age age
sort_by_ncode ncode, other_sort(inpatient age)
sort ecode
capture mkdir "`tmp_dir'/FILEPATH"
capture mkdir "`tmp_dir'/FILEPATH"
keep age draw* ecode ncode inpatient
save "`tmp_dir'/FILEPATH.dta", replace

// save YLD summary stats
fastrowmean draw*, mean_var_name("mean")
fastpctile draw*, pct(2.5 97.5) names(ll ul)
drop draw*
format mean ul ll %16.0g
order age ecode ncode inpatient mean ll ul
capture mkdir "`tmp_dir'/FILEPATH"
capture mkdir "`tmp_dir'/FILEPATH"
compress
save  "`tmp_dir'/FILEPATH.dta", replace



// End timing of this step
	end_timer, dir("`diag_dir'") name("time_`location_id'_`year'_`sex'")

// write check file to indicate sub-step has finished
	file open finished using "`tmp_dir'/FILEPATH.txt", replace write
	file close finished
	
// Erase log if successful
	log close worker
	erase "`out_dir'/FILEPATH.smcl"
	
	
