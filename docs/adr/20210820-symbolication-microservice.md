# Symbolication API as a separate microservice

- Status: accepted
- Deciders: Will Kahn-Greene
- Date: 2020-05-07
- Tags: symbolication

Proposal: https://docs.google.com/document/d/1U6FBFh9FsEWvUXf7DFzCBV4eCEjaBoxJbs9vtm6Lz6c/edit#

Tracker bug: https://bugzilla.mozilla.org/show_bug.cgi?id=1636210

## Context and Problem Statement

Tecken is the Mozilla Symbols Server and includes upload, download, and
symbolication API endpoints. In order to implement new features, we need to
rewrite the code for the symbolication API. What form should that take?

## Decision Drivers

- support different performance and uptime requirements for the service

## Considered Options

- Option 1: keep symbolication API code in Tecken monolith service
- Option 2: break symbolication API into a new microservice

## Decision Outcome

Chose "Option 2: break symbolication API into a new microservice" because
the benefits of having it separate outweigh the additional maintenance costs of
having it as a microservice.

## Pros and Cons of the Options

### Option 1: keep symbolication API code in Tecken monolith service

The symbolication API is currently part of the Tecken monolithic service. We
could keep it that way.

Goods:

- no additional maintenance costs

Bads:

- bursts of symbolication API usage continue to be a risk for upload API outage
- when implementing this, we'll be switching to the Symbolic library and
  keeping it in one big system makes that a little harder and more complex

### Option 2: break symbolication API into a new microservice

Tecken is a monolithic service that has upload, download, and symbolication
APIs. We could break the symbolication API into a separate microservice that
can run on its own.

Goods:

- we can scale the symbolication API microservice indepdently of the rest of Tecken
- bursts of symbolication API usage won't affect the upload API uptime
- potentially allows us to hand off just the symbolication API microservice to
  another group to maintain

Bads:

- each separate service requires additional maintenance to keep going: separate
  infrastructure, monitoring, deploy pipeline, project scaffolding, etc
