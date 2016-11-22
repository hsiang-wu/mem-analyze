#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt
import re
import os
import pickle
from collections import deque
from sys import argv, stdout

granularity = 30 # width of instructions that we consider to be "overlapped"
dq = deque([], granularity)
filename = "default"


def recordPhase(phases, line, lineno):
    phases.append((lineno, line[3:-4]))
    return

# return s > 1 for RW sharing, s < 0 for WW sharing. s = 1 for RR/no sharing.
def process(match):
    threadid = int(match.group(1))
    # eip = int(match.group(2), 16)
    isw = (match.group(3) == 'W') # W for write
    addr = int(match.group(4), 16)
    dq.append((threadid, addr, isw))
    tidmap = {}
    for i in dq:
        if i[1] == addr:
            if i[0] in tidmap:
                tidmap[i[0]] += isw
            else:
                tidmap[i[0]] = isw
    if len(tidmap) == 1: return 1, 'rr'

    rw, ww = False, True
    for v in tidmap.itervalues():
        if v > 0: # which means it's not read only
            rw = True
        else:
            ww = False
    if not rw: # RR or no sharing.
        return len(tidmap), 'rr'
    elif not ww:
        return len(tidmap), 'rw'
    else:
        return len(tidmap), 'ww'


def draw(xData, rrData, rwData, wwData, phases, file_size):
    plt.figure(num=1, figsize=(36, 12))
    plt.title('Plot 1', size=14)
    plt.xlabel('x-axis', size=14)
    plt.ylabel('y-axis', size=14)
    # plt.ylim([1, max(rrData)+1])
    rrmask = np.isfinite(rrData.astype(np.double))
    rwmask = np.isfinite(rwData.astype(np.double))
    wwmask = np.isfinite(wwData.astype(np.double))

    # a small trick so **Data[**mask] will never be None
    rrmask[0] = True
    rwmask[0] = True
    wwmask[0] = True

    plt.plot(xData[rrmask], rrData[rrmask], color='black', markersize=3, linestyle='None', marker='.', label='shared Read')
    plt.plot(xData[rwmask], rwData[rwmask], color='b', markersize=3, linestyle='None', marker='.', label='Read-Write')
    plt.plot(xData[wwmask], wwData[wwmask], color='r', markersize=5, linestyle='None', marker='.', label='Write-Write')
    for p in phases:
        plt.plot([p[0], p[0]], [0, 8], 'k-')
        plt.annotate(p[1], xy=(p[0], 1), 
                     xytext=(p[0], 2.5),
                     arrowprops=dict(facecolor='black', shrink=0.05))
    plt.legend(loc='upper left')
    plt.savefig('images/' + filename + 'gran=' + str(granularity) + '.png', format='png')


def read_draw():
    file_size = os.path.getsize(filename)
    print "processing ", filename, " filesize:", file_size

    pattern = re.compile("\\[(\d+)\\](0x[0-9a-f]+): ([WR]) (0x[0-9a-f]+)") 
    backup_filename = '.data.finished.granularity='+str(granularity)+'.'+filename+str(file_size)
    phases = []
    if os.path.isfile(backup_filename):
        print "reading from persistent file"
        with open(backup_filename) as f:
            i, rr, rw, ww, phases = pickle.load(f)
    else:
        with open(filename) as f:
            i = 0
            rr = []
            rw = []
            ww = [] # for write-write
            progress = 0
            nextprogress = file_size / 100
            tmpfile = "_progress_"+filename
            for line in f:
                if line.startswith("#"): continue
                if line.startswith("==="): 
                    recordPhase(phases, line, i)
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
                    sharing, mode = process(match)
                    if mode == 'rr':
                        rr.append(sharing)
                        rw.append(None)
                        ww.append(None)
                    elif mode == 'rw':
                        rr.append(None)
                        rw.append(sharing)
                        ww.append(None)
                    else: # mode == 'ww'
                        rr.append(None)
                        rw.append(None)
                        ww.append(sharing)
                    i += 1
                else:
                    print "Unmatching line", line
                    exit(0)
            stdout.write("\n")
            stdout.flush()
            os.remove(tmpfile)
        with open(backup_filename, 'wb+') as f:
            pickle.dump((i, rr, rw, ww, phases), f, pickle.HIGHEST_PROTOCOL)

    xData=np.arange(0, i, 1)
    rrData=np.array(rr)
    rwData=np.array(rw)
    wwData=np.array(ww)
    draw(xData, rrData, rwData, wwData, phases, file_size)


if __name__ == "__main__":
    filename = argv[1]
    if len(argv) > 2:
        granularity = int(argv[2])
    read_draw()
