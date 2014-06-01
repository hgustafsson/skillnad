Skillnad
========

Create visual diffs of PDF files created by LaTeX using SyncTeX.

Skillnad (english pronunciation *chill-nud*) is the Swedish word for difference and is a Python script for creating visual diffs of PDF files that have been created using LaTeX.

Unlike latexdiff, skillnad does not make changes to your original TeX-files to visually mark up the differences. Instead it uses the original PDF files and marks differences by overlaying color coded rectangles.

The positions of these rectangles in the PDF file are found using SyncTeX from the textual differences in the original TeX-files.

Dependencies
============

* Python 2
	* joblib (for running SyncTeX in parallel)
	* PyPDF2 (for finding number of pages in PDF, soon to be replaced by reading synctex-files)
* SyncTeX
* pdflatex


How to run
==========

This is an early version and unfortunately the options are currently changed by editing the python script itself. At this stage only a single TeX file can be handled per run.

The script expects the following file structure in the current working directory:

	old/
		main.tex
		main.pdf
		main.synctex.gz
	new/
		main.tex
		main.pdf
		main.synctex.gz

After running ```python skillnad.py``` in the parent directory you will obtain (among others)
	
	diff/
		diff.pdf
		merge.pdf
		
The results can then be viewed in a PDF reader by either opening ```merge.pdf``` or, alternatively, ```diff.pdf``` in "Two pages side by side" mode.

When the option ```compact``` is enabled (default) only the pages with changes on them are included in the final PDF.

See script file for further options.