import doctest
import os

def load_tests(loader, tests, ignore):
    for root, dirs, files in os.walk('screenlayout'):
        for f in files:
            if f.endswith('.py'):
                full = (root + '/' + f[:-3]).replace('/', '.')
                tests.addTests(doctest.DocTestSuite(module=full))
    return tests
