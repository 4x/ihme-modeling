// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************
// Purpose:		This master file runs the steps involved in cod/epi custom modeling for a functional group, using the steps spreadsheet as a template for launching the code
//				This master file should be used for submitting all steps or selecting one or more steps to run in "steps" global
// Description:	Correct dismod output for pre-control prevalence of infection and morbidity for the effect of mass treatment, and scale
// to the national level (dismod model is at level of population at risk).

// The output of this code is saved under the same sequela_id's as the dismod models that feed into this custom code!
// Therefore, this code requires the following types of original dismod models to be selected as best model:
//                           - lf parent: pre-control mf prevalence at level of population at risk
//                           - lymphedema: prevalence model for age pattern, based on pre-control data at level of population at risk
//                           - hydrocele: prevalence model for age pattern, based on pre-control data at level of population at risk

// qlogin -pe multi_slot 4 -l mem_free=8g -now no P- proj_custom_models
// cd FILEPATH
// git checkout dev
// git pull FILEPATH dev
// stata-mp
// do "FILEPATH"

// *********************************************************************************************************************************************************************
// *********************************************************************************************************************************************************************

// prep stata
	clear all
	set more off
	set maxvar 32000
	cap log close
	if c(os) == "Unix" {
		global prefix "FILEPATH"
		set odbcmgr unixodbc
	}
	else if c(os) == "Windows" {
		global prefix "FILEPATH"
	}

// SET GLOBALS

	// define the steps to run as space-separated list: 01 02 03a 03b (blank for all)
	local steps = "03"
	if "`steps'" == "" local steps "_all"

   // define directory that contains steps code
      local code_dir = "FILEPATH"

   // define directory that will contain results
      local out_dir = "FILEPATH"

   // define directory on clustertmp that holds intermediate files
      local tmp_dir = "FILEPATH"

   // define the date of the run in format YYYY_MM_DD: 2014_01_09
	  local date: display %tdCCYY_NN_DD date(c(current_date), "DMY")
      local date = subinstr("`date'"," ","_",.)
      local date "2018_07_07"
	// define the sequence of your steps (1=run parallelized on the cluster, 0=run in series to check intermediate results)
	local parallel 1

	// define directory that contains steps code
	if `parallel' == 0 local code_dir "STOP" // too much of this code involves the cluster
	if `parallel' == 1 local code_dir "FILEPATH"


// *****************6***************************************************************************************************************************************************
// *********************************************************************************************************************************************************************
// RUN MODEL (NO NEED TO EDIT BELOW THIS LINE)
// run model_custom
	qui run "FILEPATH/model_custom.ado"

// run model
	model_custom, code_dir("`code_dir'") out_dir("`out_dir'") tmp_dir("`tmp_dir'") date("`date'") steps("`steps'") parallel(`parallel')
