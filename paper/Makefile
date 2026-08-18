# Build the paper. Tables are generated from committed scores, never by hand.
.PHONY: all tables clean
all: tables
	pdflatex -interaction=nonstopmode main.tex
	bibtex main
	pdflatex -interaction=nonstopmode main.tex
	pdflatex -interaction=nonstopmode main.tex
tables:
	python3 make_tables.py
clean:
	rm -f main.aux main.bbl main.blg main.log main.out main.pdf
