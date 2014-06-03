#!/usr/bin/env python

from joblib import Parallel, delayed

import itertools
import subprocess
import os, re, gzip

options = {}

options["compact"] = True               # only show pages with diff
options["compact-surround"] = 0         # how many pages to add before and after compact diff
options["combine-rects"] = 0.0001       # combine diff rects

OLD = False
NEW = True

dirs = ["old", "new"]
texNames = ["main.tex", "main.tex"]
synctexNames = ["main.synctex.gz", "main.synctex.gz"]
pdfNames = ["main.pdf", "main.pdf"]
outputDir = "diff"

texFiles = [os.path.abspath(os.path.join(d,f)) for (d, f) in zip(dirs, texNames)]
synctexFiles = [os.path.abspath(os.path.join(d,f)) for (d, f) in zip(dirs, synctexNames)] 
pdfFiles = [os.path.abspath(os.path.join(d,f)) for (d, f) in zip(dirs, pdfNames)]


header = (
r"""
\coordinate (a) at ($ (current page.north east) + (0, 32) $); %
\path [fill=olive, fill opacity=0.2] (0, 0) rectangle (a); %
\node [] at ($ (0,0)!0.5!(a) $) {""" + dirs[OLD] + r"""}; %
""",
r"""
\coordinate (a) at ($ (current page.north east) + (0, 32) $); %
\path [fill=blue, fill opacity=0.2] (0, 0) rectangle (a); %
\node [] at ($ (0,0)!0.5!(a) $) {""" + dirs[NEW] + r"""}; %
""")

diffTemplate = (r"""
\documentclass[12pt]{article}

\usepackage{pdfpages}
\usepackage{tikz}
\usetikzlibrary{calc}

\begin{document}
""",
r"""

\end{document}
""")

merge = (r"""
\documentclass[12pt]{article}

\usepackage{pdfpages}
\usepackage[a4paper]{geometry}

\begin{document}
\includepdf[pages=-, nup=1x2, landscape, frame]{""",
r"""}
\end{document}
""")

# get number of pages from synctex file
def numPages(synctexFile):
     with gzip.open(synctexFile, 'rb') as f:
         return int(f.readlines()[-7][1:])

numberOfPages = [numPages(synctexFiles[age]) for age in (OLD, NEW)]

maxPages = max(numberOfPages[OLD], numberOfPages[NEW])

def findDocumentRange(tex):
    begin = 0
    end = 0
    with open(tex, "r") as f:
        for i, l in enumerate(f):
            if begin == 0 and r"\begin{document}" in l:
                begin = i
            if end == 0 and r"\end{document}" in l:
                end = i
    return set(range(begin+2, end+1))

documentRanges = [findDocumentRange(tex) for tex in texFiles]

class Rect:
    def __init__(self, page = 0, x1 = 0, y1 = 0, x2 = 0, y2 = 0):
        self.p = page
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)

    # def __cmp__(self, r):
    #     return self.x1 == r.x1 and self.y1 == r.y1 and self.x2 == r.x2 and self.y2 == r.y2

    def __add__(self, r):
        if self.p != r.p:
            raise Exception("Cannot add rects on different pages")
        if self.area() == 0:
            return r
        if r.area() == 0:
            return self
        return Rect(self.p, min(self.x1, r.x1), min(self.y1, r.y1), max(self.x2, r.x2), max(self.y2, r.y2))

    def area(self):
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    def tex(self):
        return "({0}, {1}) rectangle ({2}, {3})".format(self.x1, self.y1, self.x2, self.y2)


class Hunk:
    def __init__(self, rects = [], age = OLD):
        self.rects = []
        self.age = age
        for r in rects:
            self.addRect(r)

    def addRect(self, rect):
        if options["combine-rects"]:
            n = len(self.rects)
            matching = []
            for i, r in enumerate(self.rects):
                if(r.p == rect.p):
                    #if (not (0 < options["combine-rects"] < 1)) or ( r.area() + rect.area() > (1 - options["combine-rects"]) * (r + rect).area()):
                    if r.area() + rect.area() > (r + rect).area():
                        matching.insert(0, (i, r))
            for (i, r) in matching:
                rect = rect + r
                del self.rects[i]

        self.rects.append(rect)

    def affectedPages(self):
        return set([r.p for r in self.rects])

    def tex(self):
        return ""

class AddedHunk(Hunk):
    def tex(self, page):
        return "".join([r"\path [fill=green, fill opacity=0.2] " + r.tex() + "; % \n" for r in self.rects if r.p == page])

class DeletedHunk(Hunk):
    def tex(self, page):
        return "".join([r"\path [fill=red, fill opacity=0.2] " + r.tex() + "; % \n" for r in self.rects if r.p == page])

class ChangedHunk(Hunk):
    def tex(self, page):
        return "".join([r"\path [fill=yellow, fill opacity=0.2] " + r.tex() + "; % \n" for r in self.rects if r.p == page])


def rectsFromPdf(age, line, char):
    result = subprocess.check_output(["synctex", "view", "-i", "{0}:{1}:{2}".format(line, char, texFiles[age]), "-o", pdfFiles[age]], shell=False)

    for m in re.finditer(r"^Page:(?P<p>[0-9]+).*?h:(?P<h>[0-9.]+).*?v:(?P<v>[0-9.]+).*?W:(?P<W>[0-9.]+).*?H:(?P<H>[0-9.]+)", result, flags=re.MULTILINE | re.DOTALL):
        p = int(m.group("p"))
        h = float(m.group("h"))
        v = float(m.group("v"))
        W = float(m.group("W"))
        H = float(m.group("H"))

        yield Rect(p-1, h, v - H, h + W, v)

def createHunkPair(mode, oldLineRange, newLineRange):
    oldLineRange = documentRanges[OLD].intersection(oldLineRange)
    newLineRange = documentRanges[NEW].intersection(newLineRange)

    if mode == "a":
        return (AddedHunk(), #[rect for line in oldLineRange for rect in rectsFromPdf(OLD, line, 0)], OLD),
                AddedHunk([rect for line in newLineRange for rect in rectsFromPdf(NEW, line, 0)], NEW))
    elif mode == "d":
        return (DeletedHunk([rect for line in oldLineRange for rect in rectsFromPdf(OLD, line, 0)], OLD),
                DeletedHunk())#[rect for line in newLineRange for rect in rectsFromPdf(NEW, line, 0)], NEW))
    elif mode == "c":
        return (ChangedHunk([rect for line in oldLineRange for rect in rectsFromPdf(OLD, line, 0)], OLD),
                ChangedHunk([rect for line in newLineRange for rect in rectsFromPdf(NEW, line, 0)], NEW))

def writeTexFile(outputFile, hunkPairs):
    n = options["compact-surround"]

    texAtPage = [ [""] * maxPages, [""] * maxPages ]

    for (old, new) in hunkPairs:
        for hunk, tex in ((old, texAtPage[OLD]), (new, texAtPage[NEW])):
            for p in range(maxPages):
                tex[p] += hunk.tex(p)

    with open(outputFile, "w") as f:
        f.write(diffTemplate[0])

        for p in range(maxPages):

            if options["compact"] and all([(texAtPage[OLD][i] == "" ) and (texAtPage[NEW][i] == "") for i in range(max(p - n, 0), min(p + n + 1, maxPages))]):
                continue

            # cycle between old and new
            for (tex, pdf, pages, h) in ((texAtPage[OLD][p], pdfFiles[OLD], numberOfPages[OLD], header[OLD]), (texAtPage[NEW][p], pdfFiles[NEW], numberOfPages[NEW], header[NEW])):
                if p < pages:
                    #if tex == None:
                        #f.write(r"\includepdf[fitpaper=true, pages={" + str(p+1) + "}]{" + pdf + "}" + "\n")
                    #else:
                    f.write(r"\includepdf[fitpaper=true, pagecommand={\thispagestyle{empty}\begin{tikzpicture}[x=1pt, y=-1pt, remember picture, overlay, shift={(current page.north west)}] %")
                    f.write(h);
                    f.write(tex)
                    f.write(r"\end{tikzpicture}}, pages={" + str(p+1) + "}]{" + pdf + "}" + "\n")
                else: # out of range
                    f.write(r"\mbox{}\newpage")
                    #f.write(r"\includepdf[pages={}]{" + pdf + "}" + "\n")

        f.write(diffTemplate[1])

# takes "nr" or "nr, nr" to a range
# TODO : intersection with document range
def stringToRange(s):
    l = s.split(",")
    if len(l) == 1:
        return [int(l[0])]
    else:
        return range(int(l[0]), int(l[1])+1)


if __name__ == "__main__":
    diff = None

    print "-> Finding diffs"
    try:
        subprocess.check_output("diff " + texFiles[OLD] + " " + texFiles[NEW], shell=True)
    except subprocess.CalledProcessError, e:
        diff = e.output

    matches = re.finditer(r"^(?P<old>[0-9,]+)(?P<mode>[adc])(?P<new>[0-9,]+)", diff, re.MULTILINE)

    print "-> Making diff rects using SyncTeX"
    hunkPairs = Parallel(n_jobs=4, verbose=5)(delayed(createHunkPair)(m.group("mode"), stringToRange(m.group("old")), stringToRange(m.group("new"))) for m in matches)

    if not os.path.exists(outputDir):
        os.makedirs(outputDir)

    writeTexFile(outputDir + "/diff.tex", hunkPairs)

    with open(outputDir + "/merge.tex", "w") as f:
        f.write(merge[0] + "diff.pdf" + merge[1])

    print "-> Making PDF"
    subprocess.call(["pdflatex", "diff.tex"], cwd = outputDir, stdout=open(os.devnull, 'wb'))
    subprocess.call(["pdflatex", "diff.tex"], cwd = outputDir, stdout=open(os.devnull, 'wb'))
    subprocess.call(["pdflatex", "merge.tex"], cwd = outputDir, stdout=open(os.devnull, 'wb'))
