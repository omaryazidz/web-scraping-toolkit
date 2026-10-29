"""Menjalankan semua uji dengan output ringkas berwarna: python run_tests.py"""
import logging
import sys
import unittest

G, R, N = "\033[32m", "\033[31m", "\033[0m"


class Result(unittest.TextTestResult):
    def getDescription(self, test):
        return test.shortDescription() or str(test)

    def addSuccess(self, test):
        unittest.TestResult.addSuccess(self, test)
        self.stream.writeln(f"  {G}[PASS]{N} {self.getDescription(test)}")

    def addFailure(self, test, err):
        unittest.TestResult.addFailure(self, test, err)
        self.stream.writeln(f"  {R}[FAIL]{N} {self.getDescription(test)}")

    def addError(self, test, err):
        unittest.TestResult.addError(self, test, err)
        self.stream.writeln(f"  {R}[ERROR]{N} {self.getDescription(test)}")

    def startTest(self, test):
        unittest.TestResult.startTest(self, test)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    suite = unittest.defaultTestLoader.discover("tests")
    res = unittest.TextTestRunner(resultclass=Result, verbosity=0, stream=sys.stdout).run(suite)
    passed = res.testsRun - len(res.failures) - len(res.errors)
    print(f"== Hasil: {passed}/{res.testsRun} lulus ==")
    sys.exit(not res.wasSuccessful())
