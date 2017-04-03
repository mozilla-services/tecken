This is work in progress. The idea here is a front-end app to consume
the metrics REST data yielded from the tecken API.

## To Run In Development

Simply run:

    yarn start

Then go to http://localhost:3000

It then queries (thanks to the `proxy` setting in `package.json`) the
Django server at `http://localhost:8000/...`.


## To Keep Up To Data

To see if any dependencies are out of date run:

    yarn outdated

To upgrade any of the outdated packages run:

    yarn upgrade some-package

To add a new package, run:

    yarn add some-new-package

And if you only need it for development, run:

    yarn add --dev cool-new-package
