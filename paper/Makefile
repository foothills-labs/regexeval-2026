# Build the paper. Tables are generated from committed scores, never by hand.
.PHONY: all tables figures clean
all: tables figures
	pdflatex -interaction=nonstopmode main.tex
	bibtex main
	pdflatex -interaction=nonstopmode main.tex
	pdflatex -interaction=nonstopmode main.tex
tables:
	python3 make_tables.py
figures:
	python3 make_figures.py
clean:
	rm -f main.aux main.bbl main.blg main.log main.out main.pdf
