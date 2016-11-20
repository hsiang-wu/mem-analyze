#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt
import re
import os
from collections import deque
from sys import argv, stdout

phases = []
granularity = 100 # width of instructions that we consider to be "overlapped"
dq = deque([], granularity)
file_size = 0
filename = None


def recordPhase(line, lineno):
    phases.append((lineno, line[3:-4]))
    return


def process(match):
    threadid = int(match.group(1))
    # eip = int(match.group(2), 16)
    # op = match.group(3) # R for read, W for write
    addr = int(match.group(4), 16)
    dq.append((threadid, addr))
    tidset = set()
    for i in dq:
        if i[1] == addr:
            tidset.add(i[0])
    return len(tidset)


def draw(xData, yData):
    plt.figure(num=1, figsize=(24, 12))
    plt.title('Plot 1', size=14)
    plt.xlabel('x-axis', size=14)
    plt.ylabel('y-axis', size=14)
    plt.ylim([1, max(yData)+1])
    plt.plot(xData, yData, color='b', markersize=2, linestyle='None', marker='o', label='shared mem')
    for p in phases:
        plt.plot([p[0], p[0]], [0, 8], 'k-')
        plt.annotate(p[1], xy=(p[0], 1), 
                     xytext=(p[0], 2.5),
                     arrowprops=dict(facecolor='black', shrink=0.05))
    plt.legend(loc='upper left')
    plt.savefig('images/' + filename + '.png', format='png')


def read_draw():
    file_size = os.path.getsize(filename)
    print "processing ", filename, " filesize:", file_size

    pattern = re.compile("\\[(\d+)\\](0x[0-9a-f]+): ([WR]) (0x[0-9a-f]+)") 
    with open(filename) as f:
        i = 0
        y = []
        progress = 0
        nextprogress = file_size / 100
        tmpfile = "_progress_"+filename
        for line in f:
            if line.startswith("#"): continue
            if line.startswith("==="): 
                recordPhase(line, i)
                continue

            # the progress bar
            if f.tell() >= nextprogress:
                progress += 1
                nextprogress = file_size / 100 * (progress+1)
                stdout.write("progress: %d%%\r" % progress)
                stdout.flush()
                with open(tmpfile, 'w+') as tmp:
                    tmp.write(str(progress))


            match = pattern.match(line)
            if match:
                y.append(process(match))
                # f2.write(str(process(match)))
                # f2.write("\n")
                i += 1
            else:
                print "Unmatching line", line
                exit(0)
        stdout.write("\n")
        stdout.flush()
        os.remove(tmpfile)

        xData=np.arange(0, i, 1)
        yData=np.array(y)
        draw(xData, yData)


if __name__ == "__main__":
    filename = argv[1]
    if len(argv) > 2:
        granularity = int(argv[2])
    read_draw()
