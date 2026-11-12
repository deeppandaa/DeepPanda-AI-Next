import argparse
def add(a, b):
    return a + b
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        assert add(20, 22) == 42
    print('EXE_SUM=' + str(add(20, 22)))
