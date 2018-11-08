** ********************************************************************
** Author: 
** Date created: August 10, 2009
** Description: Combines deaths, population, and completeness and calculates 45q15
** 
** NOTE: IHME OWNS THE COPYRIGHT
** ********************************************************************

** **********************
** Set up Stata 
** **********************

	clear all 
	capture cleartmp
	set mem 500m
	set more off
    cap restore, not

	
** **********************
** Filepaths  
** **********************

	if (c(os)=="Unix") global root "/home/j"
	if (c(os)=="Windows") global root "J:"
	local version_id `1'
	global main_dir "FILEPATH"
	global both_sex_only_indicators "FILEPATH/vr_both_sex_only.csv"
	global sex_ratios "/sex_ratios.csv"
	global smoothed_comp_file = "FILEPATH/d08_final_comp.dta"
	global pop_file = "FILEPATH/d09_denominators.dta"
	global deaths_file = "FILEPATH/d01_formatted_deaths.dta"
	global save_file = "FILEPATH/d10_45q15.dta"
	
	

	import delim using "$both_sex_only_indicators", clear
	gen sex = "both"
	gen both_sex_only = 1
	tempfile both_sex_only_flags
	save `both_sex_only_flags', replace

	import delim using "$sex_ratios", clear
	tempfile sex_ratios
	save `sex_ratios', replace

	use "$deaths_file", clear

	merge 1:1 ihme_loc_id year sex source_type using `both_sex_only_flags', keep(1 3) nogen
	replace both_sex_only = 0 if mi(both_sex_only)

	preserve
	keep if both_sex_only == 1

	gen id = _n 
	expand 2
	bysort id: replace sex = "male" if _n == 1
	bysort id: replace sex = "female" if _n == 2
	drop id

	gen max_age = 0
	gen max_age_tempstore = 0
	forvalues i = 0/99 {
		replace max_age_tempstore = agegroup`i'
		replace max_age = max_age_tempstore if max_age_tempstore > max_age & max_age_tempstore != .
	}
	drop max_age_tempstore


	merge 1:1 ihme_loc_id year sex using `sex_ratios', keep(3) nogen


	forvalues j = 0/100 {
		replace deaths`j' = deaths`j' * ratio`j' if deaths`j' != . & ratio`j' != .
		replace deaths`j' = deaths`j' * ratio80plus if `j' >= max_age & `j' >= 80
		replace deaths`j' = deaths`j' * ratio60plus if `j' >= max_age & `j' < 80 & `j' >= 60
		replace deaths`j' = deaths`j' * ratio45plus if `j' >= max_age & `j' < 60 & `j' >= 45
	}

	drop max_age ratio*
	tempfile scaled_data
	save `scaled_data', replace
	restore

	append using `scaled_data'
	drop both_sex_only

	drop if sex == "both"
	drop if year < 1950

	gen openendv = .
	forvalues j = 0/99 {
		local jplus = `j'+1
		replace openendv = agegroup`j' if agegroup`jplus' == . & openendv == .
	}
	replace openendv = 100 if openendv == .
	drop if openendv < 60

	forvalues j = 0/99 {
		local jplus = `j'+1
		gen dist`j'_`jplus' = agegroup`jplus'-agegroup`j'
	}

	drop if dist0_1 == 10 | dist0_1 == 15 | dist0_1 == 25
	drop if dist1_2 == 14 | dist1_2 == 15 | dist1_2 == 19 | dist1_2 == 49

	forvalues j = 0/99 {
		local jplus = `j'+1
		drop if dist`j'_`jplus' > 10 & agegroup`j' != . & agegroup`jplus' != . & agegroup`j' < openendv	
	}

	forvalues j = 0/100 {
		rename agegroup`j' agegroupv`j'
	}

	gen max_age_gap = 0
	gen min_age_gap = 500
	gen age_gap_tempstore = 0
	forvalues i = 0/99 {
		local iplus = `i' + 1
		replace age_gap_tempstore = agegroupv`iplus' - agegroupv`i'
		replace max_age_gap = age_gap_tempstore if age_gap_tempstore > max_age_gap & age_gap_tempstore != . & agegroupv`i' > 5
		replace min_age_gap = age_gap_tempstore if age_gap_tempstore <= min_age_gap & age_gap_tempstore != . & agegroupv`i' > 5
	}


    gen vr_0to0 = deaths0
    egen vr_1to4 = rowtotal(deaths1-deaths4)
	forvalues j = 5(5)95 {
		local jplus = `j'+4
		egen vr_`j'to`jplus' = rowtotal(deaths`j'-deaths`jplus') if `j' < openendv
	}

	keep ihme_loc_id year sex country vr* deaths_source source_type deaths_nid deaths_underlying_nid hh_scaled min_age_gap max_age_gap
	sort ihme_loc_id year sex source_type
	
	replace source_type = "DSP" if regexm(source_type, "DSP") == 1 
	replace source_type = "SRS" if regexm(source_type, "SRS") == 1 
	replace source_type = "VR" if regexm(source_type, "VR") == 1 & source_type != "VR-SSA"
	
	tempfile deathdataformatted
	save `deathdataformatted', replace


	use "$smoothed_comp_file", clear

	rename source source_type
	rename final_comp comp

	rename u5_comp_pred comp_u5
    rename u5_comp comp_u5_pt_est

	tempfile ddm
	save `ddm', replace 
	

	merge 1:1 ihme_loc_id year sex source_type using `deathdataformatted'
	drop if _m == 1
	drop _m
	
	save `deathdataformatted', replace
	


	use "$pop_file", clear
	drop if sex == "both" 
	keep if source_type == "IHME" 
	keep ihme_loc_id year sex pop_source c1* pop_nid underlying_pop_nid
	tempfile pop1
	save `pop1'	

	use "$pop_file", clear
	drop if sex == "both" 
	drop if inlist(source_type, "IHME", "VR") 
	keep ihme_loc_id year sex source_type pop_source c1* pop_nid underlying_pop_nid

	tempfile pop2
	save `pop2'
	
	use `deathdataformatted', clear
	merge m:1 ihme_loc_id year sex using `pop1'
	drop if _m == 2
	drop _m 
	
	merge m:1 ihme_loc_id year sex source_type using `pop2', update replace
	drop if _m == 2
	drop _m 
	
	drop if vr_15to19 == . | c1_15to19 == . 
	


	forvalues j = 15(5)55 {
		local jplus = `j'+4
		capture: gen vr_`j'to`jplus' = .
		capture: gen c1_`j'to`jplus' = .
		gen obsasmr_`j'to`jplus' = vr_`j'to`jplus'/c1_`j'to`jplus' if vr_`j'to`jplus' != . & c1_`j'to`jplus'!= . 
	}
	
	preserve
	use "FILEPATH/BGD_SRS_1999_2005_MR_UNADJUSTED.DTA", clear
	drop if year == 2005
	append using "FILEPATH/IND_SRS_1990_1991_1995_MR_UNADJUSTED.DTA"
	append using "FILEPATH/IND_SRS_1981_2009_MR_UNADJUSTED.DTA"

	append using "FILEPATH/DZA_VR/USABLE_DZA_VR_2010_2011_MR.DTA"
    
	rename iso3 ihme_loc_id
	
	merge 1:1 ihme_loc_id year source_type sex using `ddm'
	drop if _m == 2
	drop _m
	gen pop_source = "none - mortality rates" 

	tempfile add_mr
	save `add_mr', replace
	restore 
	append using `add_mr'
	

	replace deaths_nid = "93495" if ihme_loc_id == "DZA" & year == 2010 & source_type == "VR"
	replace deaths_nid = "118440" if ihme_loc_id == "DZA" & year == 2011 & source_type == "VR"


	replace deaths_nid = "57646" if ihme_loc_id == "BGD" & inlist(year, 1990, 2004, 2006) & source_type == "SRS"


	replace deaths_nid = "33837" if ihme_loc_id== "IND" & source_type == "SRS" & inlist(year, 1981, 1982, 1983, 1984, 1985)
	replace deaths_nid = "68236" if ihme_loc_id== "IND" & source_type == "SRS" & year == 1987
	replace deaths_nid = "25080" if ihme_loc_id== "IND" & source_type == "SRS" & year == 1990
	replace deaths_nid = "33841" if ihme_loc_id== "IND" & source_type == "SRS" & year == 1991
	replace deaths_nid = "33867" if ihme_loc_id== "IND" & source_type == "SRS" & year == 1995
	replace deaths_nid = "33764" if ihme_loc_id== "IND" & source_type == "SRS" & year == 2009


    tempfile master
    save `master'
	

		use "FILEPATH/VR_data_master_file_with_cause.dta", clear

		keep iso3 year
		duplicates drop

		drop if iso3=="IND"
		** done, save wherever
		tempfile cod_years
		save `cod_years'
		

		use "FILEPATH/raw.45q15.dta", clear
		keep if regexm(source_type,"VR") 
		collapse (sum) exclude, by(ihme_loc_id year source_type)
		keep if exclude > 0
		keep ihme_loc_id year source_type
		gen outlier_45q15 = 1
		tempfile ihme_outliers
		save `ihme_outliers'
	
    use `master' if year >= 1980 & (regexm(source_type,"VR") | source_type == "DSP"), clear
    collapse (mean) comp, by(source_type ihme_loc_id year)
    split ihme_loc_id, parse("_") 
    rename ihme_loc_id1 iso3
    drop ihme_loc_id2 
    
	merge m:1 iso3 year using `cod_years', keep(3) nogen
	
	merge 1:1 ihme_loc_id year source_type using `ihme_outliers', keep(1 3) nogen
	replace outlier_45q15 = 0 if outlier_45q15 == .
	
    sort ihme_loc_id year
    outsheet using "$main_dir/cod_completeness.csv", comma replace
    
    gen comp_year_count = 1 if comp >= .95 | inlist(ihme_loc_id,"CHN_354","CHN_361")
    replace comp_year_count = 0 if comp_year_count == . | outlier_45q15 == 1
    collapse (sum) comp_year_count, by(ihme_loc_id)
    gen quality = "High" 
    replace quality = "Low" if comp < 25
    outsheet using "$main_dir/cod_comp_collapsed.csv", comma replace
	
	use `master', clear
	
	forvalues j = 15(5)55 {
		local jplus = `j'+4
			gen adjasmr_`j'to`jplus' = (1/comp)*(obsasmr_`j'to`jplus') if obsasmr_`j'to`jplus' != . 
	}


	forvalues j = 15(5)55 {
		local jplus = `j'+4
		gen obspx_`j'to`jplus' = 1-((obsasmr_`j'to`jplus'*5)/(1+2.5*obsasmr_`j'to`jplus')) 
		gen adjpx_`j'to`jplus' = 1-((adjasmr_`j'to`jplus'*5)/(1+2.5*adjasmr_`j'to`jplus')) 
	}
	
	gen obs45q15 = 1-(obspx_15to19*obspx_20to24*obspx_25to29*obspx_30to34*obspx_35to39*obspx_40to44*obspx_45to49*obspx_50to54*obspx_55to59)
	gen adj45q15 = 1-(adjpx_15to19*adjpx_20to24*adjpx_25to29*adjpx_30to34*adjpx_35to39*adjpx_40to44*adjpx_45to49*adjpx_50to54*adjpx_55to59)
	drop adjpx* obspx*
	replace adjust = 0 if adj45q15 == . | (hh_scaled == 0 & regexm(source_type, "VR") != 1 & regexm(source_type, "CENSUS") != 1)
    

	replace adj45q15 = obs45q15 if adj45q15 == . | (hh_scaled == 0 & regexm(source_type, "VR") != 1 & regexm(source_type, "CENSUS") != 1)

	replace deaths_source = "DYB" if ihme_loc_id == "DOM" & deaths_source == "WHO_causesofdeath+DYB" & inrange(year, 2007, 2010)
	replace deaths_source = "WHO_causesofdeath" if ihme_loc_id == "DOM" & deaths_source == "WHO_causesofdeath+DYB" & inrange(year, 2003, 2006) 
	
** **********************
** Format and save results 
** **********************
	
	keep ihme_loc_id source_type sex year deaths_source pop_source comp_u5_pt_est comp_u5 comp sd adjust hh_scaled obs45q15 adj45q15 vr* c1* obsasmr_* adjasmr_* *_nid min_age_gap max_age_gap
	order ihme_loc_id source_type sex year deaths_source pop_source *_nid comp_u5_pt_est comp_u5 comp sd adjust hh_scaled obs45q15 adj45q15 vr* c1* obsasmr_* adjasmr_* 
	sort ihme_loc_id source_type sex year deaths_source pop_source comp_u5_pt_est comp_u5 comp sd adjust hh_scaled obs45q15 adj45q15 vr* c1* obsasmr_* adjasmr_*
	compress

	saveold "$save_file", replace
	save "FILEPATH/d10_45q15.dta", replace

	//DONE