/*BEGIN_LEGAL 
Intel Open Source License 

Copyright (c) 2002-2016 Intel Corporation. All rights reserved.
 
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.  Redistributions
in binary form must reproduce the above copyright notice, this list of
conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.  Neither the name of
the Intel Corporation nor the names of its contributors may be used to
endorse or promote products derived from this software without
specific prior written permission.
 
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE INTEL OR
ITS CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
END_LEGAL */
/* ===================================================================== */
/*
  @ORIGINAL_AUTHOR: Robert Cohn
*/

/* ===================================================================== */
/*! @file
 *  This file contains an ISA-portable PIN tool for tracing memory accesses.
 */

#include "pin.H"
#include <iostream>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <map>

#include <sys/types.h>
#include <unistd.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <assert.h>
#include <time.h>
#include <pthread.h>
#include <errno.h>
#include <ctype.h>

#include <stdlib.h>


static inline VOID* PAGE(VOID* addr)
{
  //return (VOID *)((INT64) addr & ~0xfff);
  return addr;
}
/* ===================================================================== */
/* Global Variables */
/* ===================================================================== */

//std::ofstream TraceFile;
PIN_LOCK lock;
int fd = -1;
size_t textsize = 0;
char *  file_begin;
char ** file_in_mem; // has to be a char** because we want to share it through processes.
pid_t timer_pid;

#define mem_printf(len, ...) {char *tmp = __sync_fetch_and_add(file_in_mem, len); assert(len==sprintf(tmp, __VA_ARGS__));}

//static inline void mem_printf(const char *fmt, ...)
//{
//    va_list args;
//    va_start(args, fmt);
//    file_in_mem += vsprintf(file_in_mem, fmt, args);
//    //assert((file_in_mem - file_begin) < (int) textsize);
//}

/* ===================================================================== */
/* Commandline Switches */
/* ===================================================================== */

KNOB<string> KnobOutputFile(KNOB_MODE_WRITEONCE, "pintool",
    "o", "mytrace.out", "specify trace file name");
KNOB<INT32> KnobFileSize(KNOB_MODE_WRITEONCE, "pintool",
    "s", "0x10000000"/*256M*/, "specify memory-mapped file size");
KNOB<BOOL> KnobValues(KNOB_MODE_WRITEONCE, "pintool",
    "values", "1", "Output memory values reads and written");

//==============================================================
//  Analysis Routines
//==============================================================


/* ===================================================================== */
/* Print Help Message                                                    */
/* ===================================================================== */

static INT32 Usage()
{
    cerr <<
        "This tool produces a memory address trace.\n"
        "For each (dynamic) instruction reading or writing to memory the the ip and ea are recorded\n"
        "\n";

    cerr << KNOB_BASE::StringKnobSummary();

    cerr << endl;

    return -1;
}

PIN_LOCK record_lock;
bool silent[128]; // make it sufficiently large

static VOID RecordMem(VOID * ip, CHAR r, VOID * addr, BOOL isPrefetch, THREADID threadid)
{
    //PIN_GetLock(&lock, threadid+1);
    //    
    ////mem_printf("[%d]%lx: %lc %lx\n", threadid, (INT64) ip, r, (INT64) PAGE(addr));
    ////mem_printf("[%d]%lc %lx\n", threadid, r, (INT64) PAGE(addr));

    //// This is the bottleneck of performance. total 10 bytes
    //*file_in_mem++ = threadid; // 1 byte
    //*file_in_mem++ = r; // 1 byte
    //*(INT64 *)(file_in_mem) = (INT64) PAGE(addr); // 8 bytes
    //file_in_mem += sizeof(INT64);

    ////*file_in_mem++ = '\n';
    ////mem_printf("[%d]%lc %p\n", threadid, r, PAGE(addr));
    //PIN_ReleaseLock(&lock);

    //try this lock-free version!
    char *our_loc = __sync_fetch_and_add(file_in_mem, 2+sizeof(INT64));
    *our_loc++ = threadid; // 1 byte
    *our_loc++ = r; // 1 byte
    *(INT64 *)(our_loc) = (INT64) PAGE(addr); // 8 bytes

}

static VOID * WriteAddr;

static VOID RecordWriteAddrSize(VOID * addr)
{
    WriteAddr = addr;
}


static VOID RecordMemWrite(VOID * ip, THREADID threadid)
{
    RecordMem(ip, 'W', WriteAddr, false, threadid);
}

string phases[] = {"map", "reduce", "merge", "start_thread_pool", "edgeMap", "vertexMap"}; 
// This routine is executed each time phase is called.
VOID BeforeFunc(INT32 i, THREADID threadid )
{
    //PIN_GetLock(&lock, threadid+1);
    //TraceFile << "=== PHASE : " << phases[i] << " ===";
    //TraceFile << endl;
    int len = 9+phases[i].size();
    mem_printf(len,"=== %s ===\n", phases[i].c_str());
    //printf("=== PHASE : %s ===\n", phases[i].c_str());
    //PIN_ReleaseLock(&lock);
}

std::map<ADDRINT, int> addr_count;
//VOID BeforeQueue(ADDRINT tq, /*ADDRINT task, int lgrp, int tid,*/ THREADID threadid)
//{
//    PIN_GetLock(&lock, threadid+1);
//    if (addr_count.find(tq) == addr_count.end())
//      addr_count[tq] = 0;
//    else
//      addr_count[tq] += 1;
//    PIN_ReleaseLock(&lock);
//}


//====================================================================
// Instrumentation Routines
//====================================================================

// This routine is executed for each image.
VOID ImageLoad(IMG img, VOID *)
{
    for (int i = 0; i < 6; i++) {
      RTN rtn = RTN_FindByName(img, phases[i].c_str());
      
      if ( RTN_Valid( rtn ))
      {
          RTN_Open(rtn);
          RTN_InsertCall(rtn, IPOINT_BEFORE, AFUNPTR(BeforeFunc),
                         IARG_UINT32, i, IARG_END);
          RTN_Close(rtn);
      }
    }
}

VOID Instruction(INS ins, VOID *v)
{

    // instruments loads using a predicated call, i.e.
    // the call happens iff the load will be actually executed
        
    if (INS_IsMemoryRead(ins) && INS_IsStandardMemop(ins))
    {
        INS_InsertPredicatedCall(
            ins, IPOINT_BEFORE, (AFUNPTR)RecordMem,
            IARG_INST_PTR,
            IARG_UINT32, 'R',
            IARG_MEMORYREAD_EA,
            IARG_BOOL, INS_IsPrefetch(ins),
            IARG_THREAD_ID,
            IARG_END);
    }

    if (INS_HasMemoryRead2(ins) && INS_IsStandardMemop(ins))
    {
        INS_InsertPredicatedCall(
            ins, IPOINT_BEFORE, (AFUNPTR)RecordMem,
            IARG_INST_PTR,
            IARG_UINT32, 'R',
            IARG_MEMORYREAD2_EA,
            IARG_BOOL, INS_IsPrefetch(ins),
            IARG_THREAD_ID,
            IARG_END);
    }

    // instruments stores using a predicated call, i.e.
    // the call happens iff the store will be actually executed
    if (INS_IsMemoryWrite(ins) && INS_IsStandardMemop(ins))
    {
        INS_InsertPredicatedCall(
            ins, IPOINT_BEFORE, (AFUNPTR)RecordWriteAddrSize,
            IARG_MEMORYWRITE_EA,
            IARG_END);
        
        if (INS_HasFallThrough(ins))
        {
            INS_InsertCall(
                ins, IPOINT_AFTER, (AFUNPTR)RecordMemWrite,
                IARG_INST_PTR,
                IARG_THREAD_ID,
                IARG_END);
        }
        if (INS_IsBranchOrCall(ins))
        {
            INS_InsertCall(
                ins, IPOINT_TAKEN_BRANCH, (AFUNPTR)RecordMemWrite,
                IARG_INST_PTR,
                IARG_THREAD_ID,
                IARG_END);
        }
        
    }
}

/* ===================================================================== */

VOID Fini(INT32 code, VOID *v)
{
    mem_printf(4,"#eof");
	
    //TraceFile << "#eof" << endl;
    for (std::map<ADDRINT, int>::iterator it = addr_count.begin(); it != addr_count.end(); it++) {
      std::cout << std::hex << it->first << " , " << it->second << endl;
    }

    // ohhh... mremap is "not yet implemented" by pin...
    //mremap(file_begin, textsize, file_in_mem - file_begin, 0);
 
    // write that size back to the head of file
    *(uintptr_t *) file_begin = *file_in_mem - file_begin;
    std::cout << "actually filesize: " << std::dec << *(uintptr_t *) file_begin  << "B" << endl;
    
    //TraceFile.close();

    // Don't forget to free the mmapped memory
    if (munmap(file_begin, textsize) == -1)
    {
        close(fd);
        perror("Error un-mmapping the file");
        exit(EXIT_FAILURE);
    }
    
    // close timer child process
    int r;
    if ((r = kill(timer_pid, SIGKILL)) < 0)
        printf("can't kill child %d:%s", timer_pid, strerror(errno));
    else
        printf("kill child %d successfully\n", timer_pid);

    // Un-mmaping doesn't close the file, so we still need to do that.
    close(fd);
}

inline void open_mem_file()
{
    /* Open a file for writing.
     *  - Creating the file if it doesn't exist.
     *  - Truncating it to 0 size if it already exists. (not really needed)
     *
     * Note: "O_WRONLY" mode is not sufficient when mmaping.
     */
    assert( _POSIX_MAPPED_FILES);  
    assert( _POSIX_SYNCHRONIZED_IO);
    
    const char *filepath = KnobOutputFile.Value().c_str();
    printf("filesize: 0x%x\n", KnobFileSize.Value());

    fd = open(filepath, O_RDWR | O_CREAT | O_TRUNC, (mode_t)0600);
    
    if (fd == -1)
    {
        perror("Error opening file for writing");
        exit(EXIT_FAILURE);
    }

    // Stretch the file size to the size of the (mmapped) array of char
    textsize = KnobFileSize.Value();
    
    if (lseek(fd, textsize-1, SEEK_SET) == -1)
    {
        close(fd);
        perror("Error calling lseek() to 'stretch' the file");
        exit(EXIT_FAILURE);
    }
    
    /* Something needs to be written at the end of the file to
     * have the file actually have the new size.
     * Just writing an empty string at the current file position will do.
     *
     * Note:
     *  - The current position in the file is at the end of the stretched 
     *    file due to the call to lseek().
     *  - An empty string is actually a single '\0' character, so a zero-byte
     *    will be written at the last byte of the file.
     */
    
    if (write(fd, "", 1) == -1)
    {
        close(fd);
        perror("Error writing last byte of the file");
        exit(EXIT_FAILURE);
    }

    // Now the file is ready to be mmapped.
    file_begin = (char *) mmap(0, textsize, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);

    /* 
     * HACK: Pin prevents us from using PTHREAD, so we use process.
     * But file_in_mem must be SHARED among processes. Otherwise the lagger
     * will overwrites the file again. This is a hack trying to provide sharing
     * variable by making file_in_mem a char** instead of char*.
     *
     * file_in_mem and file_begin are not shared among processes.
     * but the region then point to are.
     *
     * | byte N  |
     * |  ....   |
     * | ------  |  
     * | byte 3  | 
     * | byte 2  | 
     * | byte 1  |  
     * | byte 0  |  <- file_begin <- file_in_mem
     */
    if (file_begin == MAP_FAILED)
    {
        close(fd);
        perror("Error mmapping the file");
        exit(EXIT_FAILURE);
    }
    file_in_mem = (char **)file_begin;
    /*
     * Then shift file_begin, so writing to file DOESN'T overwrite *file_in_mem's data.
     * Also, init the "point" value "file_in_mem" points to.
     *
     * | byte N  |
     * |  ....   |
     * | byte 4  |  <- *file_in_mem
     * | ------- |       ^         
     * | byte 3  |       |         
     * | byte 2  |       |          
     * | byte 1  |       |         
     * | byte 0  |  <- file_in_mem
     */
    *file_in_mem = file_begin + sizeof(char**);

    printf("file_begin:%p, *file_in_mem:%p\n", file_begin, *file_in_mem);
}

/* ===================================================================== */
/* Main                                                                  */
/* ===================================================================== */

int main(int argc, char *argv[])
{
    if( PIN_Init(argc,argv) )
    {
        return Usage();
    }

    open_mem_file(); // just to make it look better
    
    // Initialize the pin lock
    PIN_InitLock(&lock);

    string trace_header = string("#\n"
                                 "# Memory Access Trace Generated By Pin\n"
                                 "#\n");
    
    PIN_InitSymbols();
    for (int i = 0; i < 128; i++)
      silent[i] = 0;
    
    //TraceFile.open(KnobOutputFile.Value().c_str());
    //TraceFile.write(trace_header.c_str(),trace_header.size());
    //TraceFile.setf(ios::showbase);
 
    // can't dlopen() pthread_create. use trick instread
    //pthread_t tid;
    //int s = pthread_create(&tid, 0, &Write, 0);
    //assert(s == 0);
    
    IMG_AddInstrumentFunction(ImageLoad, 0);
    INS_AddInstrumentFunction(Instruction, 0);
    PIN_AddFiniFunction(Fini, 0);

    // Register Analysis routines to be called when a thread begins/ends
    //PIN_AddThreadStartFunction(ThreadStart, 0);
    //PIN_AddThreadFiniFunction(ThreadFini, 0);

    printf("start program and counter\n");

    // meet our timer child process!
    if ((timer_pid = fork()) == 0) { 
      // We are in the child process.
      // 1 millisecond = 1e-3 second = 1,000,000 nanoseconds
      struct timespec ts = {0, 10000000}; // 10 millisecond
      for (int i = 0; i < 10000; i++) {
          char *loc = __sync_fetch_and_add(file_in_mem,1);
          *loc = '^';
          //printf("%ld\n", loc-file_begin);
          nanosleep(&ts, NULL);
      }
      printf("exit abnormally\n");
      exit(0);
    }

    // Never returns
    PIN_StartProgram();
    
    RecordMemWrite(0, IARG_THREAD_ID);
    RecordWriteAddrSize(0);
    
    return 0;
}

/* ===================================================================== */
/* eof */
/* ===================================================================== */
