#!/usr/bin/env python

import numpy as np
import operator
import matplotlib.pyplot as plt
import re
import os
import pickle
from collections import deque
from sys import argv, stdout

ignore_addr = 0
granularity = 30 # width of instructions that we consider to be "overlapped"
dq = deque([], granularity)
xlog = []
filename = "default"

class Persistency(): # to store persistent data
    def __init__():
        pass


def recordPhase(phases, line, lineno):
    phases.append((lineno, line[3:-4]))
    return

# return s > 1 for RW sharing, s < 0 for WW sharing. s = 1 for RR/no sharing.
def process(match):
    threadid = int(match.group(1))
    # eip = int(match.group(2), 16)
    isw = (match.group(3) == 'W') # W for write
    addr = int(match.group(4), 16)
    addr = addr & ~0xfff # to page

    dq.append((threadid, addr, isw))
    if addr == ignore_addr: 
        return 1, 'ignore' # ignore. don't append
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

class AddressCount():
    def __init__(self, name):
        self.page_freq = {}
        self.name = name

    def addr_log(self, addr):
        #if addr in self.addr_freq:
        #    self.addr_freq[addr] += 1
        #else:
        #    self.addr_freq[addr] = 0
        page = addr & ~0xfff
        if page in self.page_freq:
            self.page_freq[page][0] += 1
            if addr in self.page_freq[page][1]:
                self.page_freq[page][1][addr] += 1
            else:
                self.page_freq[page][1][addr] = 0
        else:
            self.page_freq[page] = [0, # frequency
                                    {} # child addressess
                                   ]

    def write_output(self, f):
        PORTION = 0.8
        f.write("# \n")
        f.write("# Output for %s\n" % self.name)
        f.write("# \n")
        f.write("PAGE/address\t[frequency]\tportion\n")
        s = sorted(self.page_freq.items(), key=operator.itemgetter(1), reverse=True)
        s_sum = sum(map(lambda x: x[1][0], s))
        s_now = 0

        if not s:
            f.write("# Empty file: %s\n\n" % self.name)
            return

        for i in range(len(s)/4+1): # only display first 1/4
            if (s_now > PORTION * s_sum): break
            f.write("0x%x\t\t%d\t%d%%\n" % (s[i][0], s[i][1][0], s[i][1][0] * 100 / s_sum))
            s_now += s[i][1][0]

            ss = sorted(s[i][1][1].items(), key=operator.itemgetter(1), reverse=True)
            ss_sum = sum(map(lambda x: x[1], ss))
            ss_now = 0
            for j in range(len(ss)/4+1):
                if (ss_now > PORTION * ss_sum): break
                f.write("|-0x%x\t%d%%\n" % (ss[j][0], ss[j][1] * 100 / ss_sum))
                ss_now += ss[j][1]
        f.write("# End of %s\n\n" % self.name)



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
    xlog.append(0)

    plt.plot(xData[rrmask], rrData[rrmask], color='black', markersize=3, linestyle='None', marker='.', label='shared Read')
    plt.plot(xData[rwmask], rwData[rwmask], color='b', markersize=3, linestyle='None', marker='.', label='Read-Write')
    plt.plot(xData[wwmask], wwData[wwmask], color='r', markersize=5, linestyle='None', marker='.', label='Write-Write')
    print 'length of ignored:', len(xlog)
    plt.plot(np.array(xlog), np.array([3.5]*len(xlog)), color='green', markersize=2, linestyle='None', marker='.', label='ignored address')
    for p in phases:
        plt.plot([p[0], p[0]], [0, 8], 'k-')
        plt.annotate(p[1], xy=(p[0], 1), 
                     xytext=(p[0], 2.5),
                     arrowprops=dict(facecolor='black', shrink=0.05))
    plt.legend(loc='upper left')
    plt.savefig('images/' + filename + 'gran=' + str(granularity) + '.png', format='png')


def frequency_count(addrcnts):
    with open(filename+".frequency", 'w+') as f:
        for addrcnt in addrcnts:
            addrcnt.write_output(f)


def share_analyse():
    rrcnt = AddressCount("read-read share") # read-read address count
    rwcnt = AddressCount("read-write share")
    wwcnt = AddressCount("write-write share")
    file_size = os.path.getsize(filename)
    print "frequency count ", filename, " filesize:", file_size
    print "granularity:", granularity, " ignore address:", ignore_addr
    print "no draw"

    pattern = re.compile("\\[(\d+)\\](0x[0-9a-f]+): ([WR]) (0x[0-9a-f]+)") 
    phases = []
    with open(filename) as f:
        i = 0
        progress = 0
        nextprogress = file_size / 100
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

            match = pattern.match(line)
            if match:
                share_cnt, contention = process(match)
                addr = int(match.group(4), 16)
                if contention == 'rr':
                    if share_cnt > 1: rrcnt.addr_log(addr)
                if contention == 'rw': rwcnt.addr_log(addr)
                if contention == 'ww': wwcnt.addr_log(addr)
                i += 1
            else:
                print "Unmatching line", line
                exit(0)
        stdout.write("\n")
        stdout.flush()
    return [rrcnt, rwcnt, wwcnt]


def read_draw():
    file_size = os.path.getsize(filename)
    print "processing ", filename, " filesize:", file_size
    print "granularity:", granularity, " ignore address:", ignore_addr

    pattern = re.compile("\\[(\d+)\\](0x[0-9a-f]+): ([WR]) (0x[0-9a-f]+)") 
    backup_filename = '.data.finished.granularity='+str(granularity)+'.'+filename+str(file_size)
    phases = []
    if os.path.isfile(backup_filename):
        print "reading from persistent file"
        global xlog
        with open(backup_filename) as f:
            i, rr, rw, ww, xlog, phases = pickle.load(f)
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
                    if mode == 'ignore':
                        xlog.append(i)
                        rr.append(None)
                        rw.append(None)
                        ww.append(None)
                    elif mode == 'rr':
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
            pickle.dump((i, rr, rw, ww, xlog, phases), f, pickle.HIGHEST_PROTOCOL)

    xData=np.arange(0, i, 1)
    rrData=np.array(rr)
    rwData=np.array(rw)
    wwData=np.array(ww)
    draw(xData, rrData, rwData, wwData, phases, file_size)


IGNORE="--ignore"
GRAN="--granularity"
SILENT="--silent"
FREQUENCY_COUNT="-f"
if __name__ == "__main__":
    filename = argv[1]
    if GRAN in argv:
        granularity = int(argv[argv.index(GRAN)+1])
    if IGNORE in argv:
        ignore_addr = int(argv[argv.index(IGNORE)+1], 16)
    if FREQUENCY_COUNT in argv:
        counts = share_analyse()
        frequency_count(counts)
        exit(0)
    read_draw()
