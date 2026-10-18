"""Weekly check (verify.yml) that the workflows' Python is not near its end of life. Python 3.x is released each
October from 3.13 (2024) on and supported for five years, so 3.x ends in October of 2011 + x + 5. Six months
before that this fails, and the failure step opens an issue: change python-version in .github/workflows/*.yml
to the newest 3.x and let the tests run."""
import sys
from datetime import date, timedelta


def end_of_life(minor):
    return date(2011 + minor + 5, 10, 1)


def main(today=None):
    today = today or date.today()
    eol = end_of_life(sys.version_info.minor)
    if today >= eol - timedelta(days=183):
        print(f"Python 3.{sys.version_info.minor} reaches end of life around {eol:%B %Y}: change python-version in "
              f".github/workflows/*.yml to the newest 3.x release.")
        return 1
    print(f"ok: Python 3.{sys.version_info.minor} is supported until about {eol:%B %Y}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
