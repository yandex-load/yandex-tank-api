#!/usr/bin/python
import argparse

BUFFER_BYTES_IN = 300000
BUFFER_BYTES_OUT = 1000000


def phout_reader(filename):
    with open(filename, 'r', BUFFER_BYTES_IN) as f:
        while True:
            line = f.readline()
            yield (line, calculate_ts(line))


def calculate_ts(line):
    a = line.split("\t", 3)
    return float(a[0]) - float(a[2]) / 1000


def merge_phouts(filenames=None, outfilename='result_phout.txt'):
    if filenames is None:
        filenames = []
    readers = []
    current = []
    left_files = []

    for i in range(len(filenames)):
        reader = phout_reader(filenames[i])
        readers.append(reader)
        try:
            current.append(next(reader))
            left_files.append(i)
        except:
            pass

    with open(outfilename, 'w', BUFFER_BYTES_OUT) as outfile:
        while len(left_files):
            i = min(left_files, key=lambda x: current[x][1])
            outfile.write(current[i][0])
            try:
                current[i] = next(readers[i])
            except:
                left_files.remove(i)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='-i=FILE1.txt,FILE2.txt,FILE3.txt -o RESULT.txt')
    parser.add_argument('-i', action='store', dest='in_files', type=str)
    parser.add_argument('-o', action='store', dest='outfilename', type=str)

    args = parser.parse_args()
    in_files = args.in_files.split(',')
    merge_phouts(in_files, args.outfilename)
