GENERAL INFORMATION

1. Title of Dataset: Supporting data for McHugh et al. 2023, “Using Large Ensembles to Examine Historical and Projected Changes in Record-Breaking Summertime Temperatures over the Contiguous United States.”

2. Creators/Author list Information
	A. Principal Investigator Contact Information
		Name:  Colleen E. McHugh
		Institution: Science Applications International Corporation
		Address: 201 Forrestal Road, Princeton, NJ 08540
		Email: colleen.mchugh@noaa.gov

	B. Co-authors: 
		Name: Thomas L. Delworth
		Institution: NOAA Geophysical Fluid Dynamics Laboratory
		Email: tom.delworth@noaa.gov

# NOTE: Co-authors William Cooke and Liwei Jia are omitted on purpose here to test extraction filters.
# NOTE: External user inquiries instructions are completely omitted from this test file on purpose.

3. Date of data collection: 2017, 2020-2021

4. Geographic location of data collection: The Geophysical Fluid Dynamics Laboratory (GFDL) of the National Oceanic and Atmospheric Administration (NOAA) in Princeton, NJ.

# NOTE: Section 5 (Information about funding sources) is missing on purpose.


SHARING/ACCESS INFORMATION

1. Licenses/restrictions placed on the data:
These data were produced by NOAA and are not subject to copyright protection in the United States. NOAA waives any potential copyright and related rights in these data worldwide through the Creative Commons Zero 1.0 Universal Public Domain Dedication (CC0-1.0). 

2. Links to publications that were used as references, or that cite or use the data:
Delworth, T. L., Cooke, W. F., Adcroft, A., Bushuk, M., Chen, J.-H., Dunne, K. A., et al. (2020). SPEAR: The Next Generation GFDL Modeling System for Seasonal to Multidecadal Prediction and Projection. Journal of Advances in Modeling Earth Systems, 12(3), e2019MS001895. https://doi.org/10.1029/2019MS001895

# NOTE: Publicly accessible locations (3), ancillary data links (4), and derived sources (5) are missing on purpose.

6. Recommended citation for this dataset: Colleen E. McHugh, Thomas L. Delworth, William Cooke, Liwei Jia (2023). Supporting data for McHugh et al., 2023 [Data set]. Geophysical Fluid Dynamics Laboratory, November, 2023.


DATA & FILE OVERVIEW

1. File List: 
The directory contains a list of individual compressed tar.gz files organized by file name consisting of the model, experiment, model component, frequency, and variable as follows for the GFDL FLOR and SPEAR models:
flor.experiment.component_frequency.variable.tar.gz
spear.experiment.component_frequency.variable.tar.gz

# NOTE: Relationship between files (2), Additional related data (3), and Multiple versions (4) are missing on purpose.


METHODOLOGICAL INFORMATION

1. Description of methods used for collection/generation of data: 
This dataset contains model output from the coupled global climate models SPEAR and FLOR, both developed at GFDL. For more information on the model designs, see Delworth et al. (2020) and Vecchi et al. (2014) for SPEAR and FLOR respectively.

2. Methods for processing the data: 
The simulations were performed on the GAEA supercomputer at Oak Ridge National Laboratory (ORNL), Oak Ridge, TN. Raw model output was post-processed at NOAA GFDL using the FMS Runtime Environment (FRE). 

# NOTE: Instrument info (3), Standards/Calibration (4), Environmental conditions (5), and QA procedures (6) are missing on purpose.

7. People involved with sample collection, processing, analysis and/or submission: 
Co-authors listed on this dataset: Colleen E. McHugh, Thomas L. Delworth, William Cooke, Liwei Jia


DATA-SPECIFIC INFORMATION FOR: NetCDF files in tar.gz files

1. Number of variables: 1

3. Variable List: 
t_ref_max; maximum temperature; K

