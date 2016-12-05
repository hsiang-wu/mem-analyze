#!/usr/bin/env python

import numpy as np
import operator
import matplotlib.pyplot as plt
import re
import os
import struct
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


class AddressCount():
    def __init__(self, name):
        self.page_freq = {}
        self.name = name

    def addr_log(self, addr, count=1):
        #if addr in self.addr_freq:
        #    self.addr_freq[addr] += 1
        #else:
        #    self.addr_freq[addr] = 0
        page = addr & ~0xfff
        if page in self.page_freq:
            self.page_freq[page][0] += count
            if addr in self.page_freq[page][1]:
                self.page_freq[page][1][addr] += count
            else:
                self.page_freq[page][1][addr] = count
        else:
            self.page_freq[page] = [0, # frequency
                                    {} # child addressess
                                   ]

    def write_output(self, f):
        PORTION = 0.9
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
            if s_sum == 0: break
            f.write("0x%x\t\t%d\t%d%%\n" % (s[i][0], s[i][1][0], s[i][1][0] * 100 / s_sum))
            s_now += s[i][1][0]

            ss = sorted(s[i][1][1].items(), key=operator.itemgetter(1), reverse=True)
            ss_sum = sum(map(lambda x: x[1], ss))
            ss_now = 0
            for j in range(len(ss)/4+1):
                if (ss_now > PORTION * ss_sum): break
                if ss_sum: f.write("|-0x%x\t%d%%\n" % (ss[j][0], ss[j][1] * 100 / ss_sum))
                ss_now += ss[j][1]
        f.write("# End of %s\n\n" % self.name)

    @staticmethod
    def frequency_count(addrcnts):
        print "creating file",filename,".frequency"
        with open(filename+".frequency", 'w+') as f:
            for addrcnt in addrcnts:
                addrcnt.write_output(f)


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



class Analyse():
    def __init__(self, filename, havetimesig=True, try_backup=True):
        """
        havetimesig: whether the file contains "^" to indicate a time interval
        
        try_backup: if set, we'll try to restore backup file
        on the disk (if possible). Otherwise we'll do it again from scratch
        """
        self.filename = filename
        self.file_size = os.path.getsize(self.filename)
        self.havetimesig = havetimesig

        self.tlog = TimeLog("all")
        self.tlog_i = TimeLog("ignore") # times that filter out ignores

        self.try_backup = try_backup
        self.backup_filename = filename+'.sz='+str(self.file_size)
        self.backup=[]

        self.rrcnt = AddressCount("read-read share") # read-read address count
        self.rwcnt = AddressCount("read-write share")
        self.wwcnt = AddressCount("write-write share")
        self.ignores = []

        self.l = {}
        self.l_i = {}
        self.phases=[]

    def add_ignore(self, ignored):
        self.ignores.append(ignored)

    def file_pattern(self, f):
        assert(False)

    def restore(self):
        if self.try_backup:
            if os.path.isfile(self.backup_filename):
                print "reading from persistent file"
                with open(self.backup_filename) as f:
                    self.backup = pickle.load(f)
                    self.tlog = self.backup[3]
                    self.tlog_i = self.backup[4]
                    self.phases = self.backup[5]
                    self.backup = self.backup[0:3]
                    return True
        return False

    def make_backup(self):
        self.backup = [self.rrcnt, self.rwcnt, self.wwcnt, self.tlog, self.tlog_i, self.phases]
        with open(self.backup_filename, 'wb+') as f:
            pickle.dump(self.backup, f, pickle.HIGHEST_PROTOCOL)

    def share_analyse(self):
        print "frequency count ", self.filename, " filesize:", self.file_size
        print "granularity:", granularity, " ignore address:", self.ignores
        print "no draw"
    
        if self.restore(): # if there is disk backup, read from it
            return self.backup # don't have to process again!

        with open(filename) as f:
            return self.file_pattern(f)

    def draw_timestat(self):
        plt.figure(num=1, figsize=(18, 12))
        plt.title('Plot 1', size=14)
        plt.xlabel('x-axis', size=14)
        plt.ylabel('y-axis', size=14)
        # plt.ylim([1, max(rrData)+1])

        self.tlog.draw()
        if self.ignores: # if not []
            print "draw ignored"
            self.tlog_i.draw()
        for p in self.phases:
            plt.annotate(p[1], xy=(p[0], 1), 
                         xytext=(p[0], max(self.tlog.wstats)/5),
                         arrowprops=dict(facecolor='black', shrink=0.05))
        plt.legend(loc='upper left')
        plt.savefig('images/' + 'img.' + self.backup_filename + '.png', format='png')

    def record_interval(self):
        self.tlog.new_interval(self.rrcnt, self.wwcnt)
        self.tlog_i.new_interval()

    @staticmethod
    def process(threadid, isw, addr):
        """ return s > 1 for RW sharing, s < 0 for WW sharing. s = 1 for RR/no sharing.
        """
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

class TimeLog:
    def __init__(self, name="default timelog"):
        self.name = name
        self.curr_window = {} # current window
        self.rostats = [] # log of all read-only conflicts
        self.wstats = [] # log of all r-w/w-w conflicts

    def draw(self, ls='-'):
        xData = np.array(range(len(self.rostats)))
        yData = np.array(np.array(self.rostats))
        plt.plot(xData, yData, color=np.random.rand(3,1), markersize=3, linestyle=ls, marker='.', label=self.name+" shared-read")
        xData = np.array(range(len(self.wstats)))
        yData = np.array(np.array(self.wstats))
        plt.plot(xData, yData, color=np.random.rand(3,1), markersize=5, linestyle='--', marker='x', label=self.name+" rw/ww")

    def new_interval(self, rrcnt=None, wwcnt=None):
        wstat, rostat = 0, 0
        for page in self.curr_window:
            tids, ops = self.curr_window[page]
            if len(tids) == 1: continue
            not_ro = sum(ops) # if all op is read then sum is 0
            if not_ro:
                wstat += len(ops)
                if wwcnt: wwcnt.addr_log(page, len(ops))
            else:
                rostat += len(ops)
                if rrcnt: rrcnt.addr_log(page, len(ops))
        self.rostats.append(rostat)
        self.wstats.append(wstat)
        self.curr_window.clear()

    def log(self, isw, page, tid):
        if page in self.curr_window:
            self.curr_window[page][0].add(tid)
            self.curr_window[page][1].append(isw)
        else:
            self.curr_window[page] = [set([tid]), []]
            self.curr_window[page][1] = [isw]

class StrAnalyse(Analyse):
    # overwritten
    def file_pattern(self, f):
        pattern = re.compile("\\[(\d+)\\](0x[0-9a-f]+): ([WR]) (0x[0-9a-f]+)") 
        phases = []
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
                threadid = int(match.group(1))
                isw = (match.group(3) == 'W') # W for write
                addr = int(match.group(4), 16)
                share_cnt, contention = Analyse.process(threadid, isw, addr)

                if contention == 'rr':
                    if share_cnt > 1: self.rrcnt.addr_log(addr)
                if contention == 'rw': self.rwcnt.addr_log(addr)
                if contention == 'ww': self.wwcnt.addr_log(addr)
                i += 1
            else:
                print "Unmatching line", line
                exit(0)
        stdout.write("\n")
        stdout.flush()
        return [self.rrcnt, self.rwcnt, self.wwcnt]
    

class BinAnalyse(Analyse):
    def process_time(self, tid, isw, addr):
        page = addr & ~0xfff # to page

        self.tlog.log(isw, page, tid)
        if page not in self.ignores:
            self.tlog_i.log(isw, page, tid)

    def log_timestamp(self, ts):
        pass

    # overwritten
    def file_pattern(self, f):
        i = 0
        progress = 0
        file_size = struct.unpack("<Q", f.read(8))[0]
        stdout.write( "size of binary file: %d\n" % file_size )
        nextprogress = file_size / 100
        while f:
            # the progress bar
            if f.tell() >= nextprogress:
                progress += 1
                nextprogress = file_size / 100 * (progress+1)
                stdout.write("progress: %d%%\r" % progress)
                stdout.flush()

            tid = f.read(1)
            if tid == '#':
                if 'eof' in f.readline():
                    break
            if tid == '=':
                recordPhase(self.phases, tid+f.readline(), i)
                continue

            line = f.read(17) # 1 byte for W/R, 8 for addr, 8 for timestamp
            threadid = ord(tid)
            if (threadid > 10):
                stdout.write("error threadid:%d" % threadid)
            isw = (line[0] == 'W')
            addr = struct.unpack("<Q", line[1:9])[0] # 8 byte to int
            timestamp = struct.unpack("<Q", line[9:])[0] # < for little-endian, Q for unsigned 8 bytes
            self.log_timestamp(timestamp)

            share_cnt, contention = Analyse.process(threadid, isw, addr)
            
            if contention == 'rr':
                if share_cnt > 1: self.rrcnt.addr_log(addr)
            if contention == 'rw': self.rwcnt.addr_log(addr)
            if contention == 'ww': self.wwcnt.addr_log(addr)

            i += 1

        self.record_interval()
        self.make_backup()
        stdout.write("\n")
        stdout.flush()
        return [self.rrcnt, self.rwcnt, self.wwcnt]


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
                    sharing, mode = Analyse.process(match)
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
TIMSIG='-t'
BIN='-b'
NEW='--new'
if __name__ == "__main__":
    filename = argv[1]
    if GRAN in argv:
        granularity = int(argv[argv.index(GRAN)+1])

    if BIN in argv:
        a = BinAnalyse(filename=filename, havetimesig=TIMSIG in argv, try_backup= not NEW in argv) # compressed output file
    else:
        a = StrAnalyse(filename)

    if IGNORE in argv:
        i = argv.index(IGNORE)+1
        while i < len(argv) and not argv[i].startswith('-'):
            ignore_addr = int(argv[i], 16)
            #a.add_ignore(ignore_addr)
            a.add_ignore(ignore_addr & ~0xfff)
            i+=1


    if FREQUENCY_COUNT in argv:
        counts = a.share_analyse()
        AddressCount.frequency_count(counts)
        a.draw_timestat()
        exit(0)

    read_draw()
