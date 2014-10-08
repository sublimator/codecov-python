#!/usr/bin/python

import os
import re
import sys
import requests
import argparse
import subprocess
from json import dumps

try:
    from urllib.parse import urlencode
except ImportError: # pragma: no cover
    from urllib import urlencode

version = VERSION = __version__ = '1.0.2'

SKIP_DIRECTORIES = re.compile(r'\/?(\..+|(virtualenv|venv\/(lib|bin)|build\/lib|\.git|\.egg\-info))\/')
SKIP_FILES = re.compile(r'(\.tar\.gz|\.pyc|\.egg|(\/\..+)|\.txt)$')

def build_reports(root):
    # (python)
    try_to_run('coverage xml')

    reports = []
    table_of_contents = []
    accepting = set(('coverage.xml', 'clover.xml', 'coverage.txt', 'cobertura.xml', 'jacoco.xml', 'coverage.lcov', 'coverage.gcov'))
    for _root, dirs, files in os.walk(root):
        print "\033[92m....\033[0m", _root, SKIP_DIRECTORIES.search(_root), files
        if SKIP_DIRECTORIES.search(_root): continue
        # add data to tboc
        for _file in files:
            fp = os.path.join(_root, _file).replace(root+"/", '')
            if not (SKIP_DIRECTORIES.search(fp) or SKIP_FILES.search(fp)) and '/' in fp:
                table_of_contents.append(fp)
        # is there a coverage report?
        for coverage in (accepting & set(files)):
            with open(os.path.join(_root, coverage), 'r') as coverage_file:
                reports.append(coverage_file.read())

    print "\033[92m....\033[0m", reports
    assert len(reports) > 0, "error no coverage report found, could not upload to codecov"

    # add out table of contents
    reports.insert(0, "\n".join(table_of_contents))
    # join reports together
    return "\n<<<<<< EOF\n".join(reports)

def try_to_run(cmd):
    try:
        subprocess.check_output(cmd, shell=True)
    except:
        pass

def upload(url, root, **kwargs):
    try:
        if not root:
            root = os.getcwd()
        args = dict(commit='', branch='', travis_job_id='')
        args.update(kwargs)
        assert args.get('branch') not in ('', None), "branch is required"
        assert args.get('commit') not in ('', None), "commit hash is required"
        assert any((args.get('travis_job_id'),
                   (args.get('build') and args.get('service')=='circleci'),
                   args.get('token'))), "missing token or other required argument(s)"

        reports = build_reports(root)

        assert reports, "error no coverage report found, could not upload to codecov"

        kwargs['package'] = "codecov-v%s" % VERSION

        url = "%s/upload/v2?%s" % (url, urlencode(dict([(k, v.strip()) for k, v in kwargs.items() if v is not None])))
        result = requests.post(url, data=reports)
        result.raise_for_status()
        return result.json()

    except AssertionError as e:
        return dict(message=str(e), uploaded=False, coverage=0)

def main(*argv):
    defaults = dict(commit='', branch='', travis_job_id='', root=None, pull_request='', build_url='')

    # -------
    # Jenkins
    # -------
    if os.getenv('JENKINS_URL'):
        # https://wiki.jenkins-ci.org/display/JENKINS/Building+a+software+project
        defaults.update(dict(branch=os.getenv('GIT_BRANCH'),
                             service='jenkins',
                             commit=os.getenv('GIT_COMMIT'),
                             build=os.getenv('BUILD_NUMBER'),
                             root=os.getenv('WORKSPACE'),
                             build_url=os.getenv('BUILD_URL')))
    # ---------
    # Travis CI
    # ---------
    elif os.getenv('CI') == "true" and os.getenv('TRAVIS') == "true":
        # http://docs.travis-ci.com/user/ci-environment/#Environment-variables
        defaults.update(dict(branch=os.getenv('TRAVIS_BRANCH'),
                             service='travis-org',
                             build=os.getenv('TRAVIS_JOB_NUMBER'),
                             pull_request=os.getenv('TRAVIS_PULL_REQUEST') if os.getenv('TRAVIS_PULL_REQUEST')!='false' else '',
                             travis_job_id=os.getenv('TRAVIS_JOB_ID'),
                             owner=os.getenv('TRAVIS_REPO_SLUG').split('/',1)[0],
                             repo=os.getenv('TRAVIS_REPO_SLUG').split('/',1)[1],
                             root=os.getenv('TRAVIS_BUILD_DIR'),
                             commit=os.getenv('TRAVIS_COMMIT')))
    # --------
    # Codeship
    # --------
    elif os.getenv('CI') == "true" and os.getenv('CI_NAME') == 'codeship':
        # https://www.codeship.io/documentation/continuous-integration/set-environment-variables/
        defaults.update(dict(branch=os.getenv('CI_BRANCH'),
                             service='codeship',
                             build=os.getenv('CI_BUILD_NUMBER'),
                             build_url=os.getenv('CI_BUILD_URL'),
                             commit=os.getenv('CI_COMMIT_ID')))
    # ---------
    # Circle CI
    # ---------
    elif os.getenv('CI') == "true" and os.getenv('CIRCLECI') == 'true':
        # https://circleci.com/docs/environment-variables
        defaults.update(dict(branch=os.getenv('CIRCLE_BRANCH'),
                             service='circleci',
                             build=os.getenv('CIRCLE_BUILD_NUM'),
                             owner=os.getenv('CIRCLE_PROJECT_USERNAME'),
                             repo=os.getenv('CIRCLE_PROJECT_REPONAME'),
                             commit=os.getenv('CIRCLE_SHA1')))
    # ---------
    # Semaphore
    # ---------
    elif os.getenv('CI') == "true" and os.getenv('SEMAPHORE') == "true":
        # https://semaphoreapp.com/docs/available-environment-variables.html
        defaults.update(dict(branch=os.getenv('BRANCH_NAME'),
                             service='semaphore',
                             build=os.getenv('SEMAPHORE_BUILD_NUMBER'),
                             owner=os.getenv('SEMAPHORE_REPO_SLUG').split('/',1)[0],
                             repo=os.getenv('SEMAPHORE_REPO_SLUG').split('/',1)[1],
                             commit=os.getenv('SEMAPHORE_PROJECT_HASH_ID')))
    # --------
    # drone.io
    # --------
    elif os.getenv('CI') == "true" and os.getenv('DRONE') == "true":
        # http://docs.drone.io/env.html
        defaults.update(dict(branch=os.getenv('DRONE_BRANCH'),
                             service='drone.io',
                             build=os.getenv('BUILD_ID'),
                             build_url=os.getenv('DRONE_BUILD_URL'),
                             commit=os.getenv('DRONE_COMMIT')))
    # ---
    # git
    # ---
    else:
        # find branch, commit, repo from git command
        branch = subprocess.check_output('git rev-parse --abbrev-ref HEAD', shell=True)
        defaults.update(dict(branch=branch if branch != 'HEAD' else 'master',
                             commit=subprocess.check_output('git rev-parse HEAD', shell=True)))

    parser = argparse.ArgumentParser(prog='codecov', add_help=True,
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="""Read more at https://codecov.io/""")
    parser.add_argument('--version', action='version', version='codecov '+version+" - https://codecov.io")
    parser.add_argument('--commit', default=defaults.pop('commit'), help="commit ref")
    parser.add_argument('--min-coverage', default="0", help="min coverage goal, otherwise build fails")
    parser.add_argument('--branch', default=defaults.pop('branch'), help="commit branch name")
    parser.add_argument('--token', '-t', default=os.getenv("CODECOV_TOKEN"), help="codecov repository token")
    parser.add_argument('--url', default=os.getenv("CODECOV_ENDPOINT", "https://codecov.io"), help="url for enteprise customers")
    if argv:
        codecov = parser.parse_args(argv)
    else:
        codecov = parser.parse_args()
    
    data = upload(url=codecov.url, branch=codecov.branch, commit=codecov.commit, token=codecov.token, **defaults)
    return data, int(codecov.min_coverage)

def cli():
    data, min_coverage = main()
    data['version'] = version
    sys.stdout.write(dumps(data)+"\n")
    if int(data['coverage']) >= min_coverage:
        sys.exit(0)
    else:
        sys.exit("requiring %s%% coverage, commit resulted in %s%%" % (str(min_coverage), str(data['coverage'])))

if __name__ == '__main__':
    cli()
