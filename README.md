# Tecken - All things Mozilla Symbol Server

[![CircleCI](https://circleci.com/gh/mozilla-services/tecken.svg?style=svg)](https://circleci.com/gh/mozilla-services/tecken)
[![Updates](https://pyup.io/repos/github/mozilla-services/tecken/shield.svg)](https://pyup.io/repos/github/mozilla-services/tecken/)
[![Renovate enabled](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovateapp.com/)
[![What's Deployed](https://img.shields.io/badge/whatsdeployed-dev,stage,prod-green.svg)](https://whatsdeployed.io/s-5HY)
[![Code style](https://img.shields.io/badge/Code%20style-black-000000.svg)](https://github.com/ambv/black)

Please use the documentation on: **https://tecken.readthedocs.io**

The **production server** is: https://symbols.mozilla.org

## To Get Coding

You need to be able to run Docker.

Git clone and then run:

    make build
    make run

Now a development server should be available at `http://localhost:3000`.

To test the symbolication run:

    curl -d '{"stacks":[[[0,11723767],[1, 65802]]],"memoryMap":[["xul.pdb","44E4EC8C2F41492B9369D6B9A059577C2"],["wntdll.pdb","D74F79EB1F8D4A45ABCD2F476CCABACC2"]],"version":4}' http://localhost:8000

## Datadog

If you have access to a Mozilla Cloud Ops Datadog account, use this to
consume the metrics Tecken sends via `statsd`. One is for staying health, the other is for
keeping track how it does things.

[Tecken Operations](https://app.datadoghq.com/dash/286319/tecken)

[Tecken Performance](https://app.datadoghq.com/dash/339351/tecken-performance)

[Tecken Redis](https://app.datadoghq.com/screen/190509/tecken-redis)

[Redis Store Prod](https://app.datadoghq.com/dash/857077?live=true&page=0&is_auto=false&from_ts=1533210569870&to_ts=1533296969870&tile_size=m)

[Symbols RDS](https://app.datadoghq.com/screen/280710/symbols-rds)

## New Relic

This requires you have access to the
[Mozilla_25 New Relic account](https://rpm.newrelic.com/accounts/1402187/applications).

[symbols-prod](https://rpm.newrelic.com/accounts/1402187/applications/62681492)

[symbols-stage](https://rpm.newrelic.com/accounts/1402187/applications/52227224)

## Whatsdeployed

Check out https://whatsdeployed.io/s-5HY

## The Logo

![logo](logo.png "The Logo")

The [logo](https://www.iconfinder.com/icons/118754/ampersand_icon) comes from
[P.J. Onori](http://www.somerandomdude.com/) and is licensed under
[Attribution-Non-Commercial 3.0 Netherlands](http://creativecommons.org/licenses/by-nc/3.0/nl/deed.en_GB).
