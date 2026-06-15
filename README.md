# spear-esm-data-automation
Automating the data lifecycle for NOAA GFDL's SPEAR Earth System Model using LLMs to generate documentation and quality-control outputs.


### How to use: 

1. Download all dependacies in environment.yml, python version 3.11


2. Add your api key to the .env.example, then rename to .env


3. run the ipynb inside of the notebooks folder, it should create a folder called inputs


4. Put all the documents you want to be analyzed in the inputs folder, and then configure the questions you want to be answered.


Note: the DMP format and the READme formats have not been implemented, they must be done manually which I haven't done yet
In the mean time, upload any supported document, and then make your own questions by tweaking configs under 
the DOCUMENT TEMPLATES dictionary. 

