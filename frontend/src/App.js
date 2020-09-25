/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */
import React from "react";
import "./App.css";
import {
  BrowserRouter as Router,
  Route,
  Redirect,
  Switch,
  Link,
} from "react-router-dom";
import { withRouter } from "react-router";
import Raven from "raven-js";
import { observer } from "mobx-react";
import "bulma/css/bulma.css";

import Nav from "./Nav";
import Home from "./Home";
import Help from "./Help";
import Tokens from "./Tokens";
import Uploads from "./Uploads";
import DownloadsMissing from "./DownloadsMissing";
import Upload from "./Upload";
import UploadNow from "./UploadNow";
import Files from "./Files";
import File from "./File";
import Symbolication from "./Symbolication";
import FetchError from "./FetchError";
import Fetch from "./Fetch";
import DisplayAPIRequests from "./APIRequests";
import store from "./Store";

if (process.env.REACT_APP_SENTRY_PUBLIC_DSN) {
  Raven.config(process.env.REACT_APP_SENTRY_PUBLIC_DSN).install();
}

const NavWithRouter = withRouter(Nav);

const App = observer(
  class App extends React.Component {
    constructor(props) {
      super(props);
      this.state = {
        redirectTo: null,
      };
    }

    componentWillMount() {
      this._fetchAuth();
    }

    _fetchAuth = () => {
      Fetch("/api/_auth/").then((r) => {
        if (r.status === 200) {
          if (store.fetchError) {
            store.fetchError = null;
          }
          r.json().then((response) => {
            if (response.user) {
              store.currentUser = response.user;
              store.signOutUrl = response.sign_out_url;
              if (
                document.location.search.match(/signedin=true/) &&
                !sessionStorage.getItem("signedin")
              ) {
                sessionStorage.setItem("signedin", true);
                // you have just signed in
                store.setNotificationMessage(
                  `You have signed in as ${response.user.email}`
                );
              }
            } else {
              store.signInUrl = response.sign_in_url;
            }
          });
        } else {
          store.fetchError = r;
        }
      });
    };

    adminLink = () => {
      // Need to figure out the right url that works in the local dev environment
      // which does this proxy thing
      let here = window.location;
      let url =
        here.protocol + "//" + here.hostname + ":" + here.port + "/admin";
      // Replace proxy webpack host with django host in local dev environment
      url = url.replace("http://localhost:3000/", "http://localhost:8000/");
      return url;
    };

    signIn = (event) => {
      event.preventDefault();
      let url = store.signInUrl;
      /* When doing local development, the Django runserver is
         running at 'http://web:8000', in Docker, as far as the React dev
         server is concerned. That doesn't work outside Docker
         (i.e on the host) so we'll replace this.
         It's safe since the string replace is hardcoded and only does
         something if the original URL matched.
         */
      url = url.replace("http://web:8000/", "http://localhost:8000/");
      document.location.href = url;
    };

    signOut = (event) => {
      event.preventDefault();
      let url = store.signOutUrl;
      // See above explanation, in 'signIn()' about this "hack"
      url = url.replace("http://web:8000/", "http://localhost:3000/");
      Fetch(url, {
        method: "POST",
        redirect: "manual",
      }).then((r) => {
        sessionStorage.removeItem("signedin");
        store.currentUser = false;
        store.setRedirectTo("/", {
          message: "Signed out",
          success: true,
        });
        // This'll refetch the signInUrl
        this._fetchAuth();
      });
    };

    render() {
      // The reason we make this conditional first, rather than letting
      // RedirectMaybe be its own observer, is that this way we can
      // *immediately* do an "early exit" if it's set to something.
      if (store.redirectTo) {
        return (
          <Router>
            <RedirectMaybe redirectTo={store.redirectTo} />
          </Router>
        );
      }
      return (
        <Router>
          <React.Fragment>
            <NavWithRouter
              signIn={this.signIn}
              signOut={this.signOut}
              adminLink={this.adminLink}
            />
            <section className="section">
              <div className="container">
                <DisplayNotificationMessage
                  message={store.notificationMessage}
                />
                <FetchError error={store.fetchError} />
                <Switch>
                  <Route
                    path="/"
                    exact
                    render={(props) => {
                      return <Home {...props} signIn={this.signIn} />;
                    }}
                  />
                  <Route path="/help" component={Help} />
                  <Route path="/tokens" component={Tokens} />
                  <Route
                    path="/downloads/missing/"
                    component={DownloadsMissing}
                  />
                  <Route path="/uploads/files" exact component={Files} />
                  <Route path="/uploads/files/file/:id" component={File} />
                  <Route path="/uploads/upload" exact component={UploadNow} />
                  <Route path="/uploads/upload/:id" component={Upload} />
                  <Route path="/uploads" exact component={Uploads} />
                  <Route path="/symbolication" component={Symbolication} />
                  <Route component={NoMatch} />
                </Switch>

                <DisplayAPIRequests />
              </div>
            </section>
            <footer className="footer">
              <div className="container">
                <div className="content has-text-centered">
                  <p>
                    <strong>The Mozilla Symbol Server</strong>
                    <br />
                    Powered by{" "}
                    <a
                      href="https://github.com/mozilla-services/tecken"
                      rel="noopener noreferrer"
                    >
                      Tecken
                    </a>
                    {" • "}
                    <a
                      href="https://tecken.readthedocs.io"
                      rel="noopener noreferrer"
                    >
                      Documentation
                    </a>
                  </p>
                </div>
              </div>
            </footer>
          </React.Fragment>
        </Router>
      );
    }
  }
);

export default App;

class NoMatch extends React.PureComponent {
  render() {
    return (
      <div>
        <h1 className="title">Page Not Found</h1>
        <h2>
          No page found <code>{this.props.location.pathname}</code>.
        </h2>
        <h2>
          <Link to="/">Go back to Home</Link>
        </h2>
      </div>
    );
  }
}

class RedirectMaybe extends React.PureComponent {
  componentDidMount() {
    if (this.props.redirectTo) {
      // tell the store we've used it
      store.redirectTo = null;
    }
  }
  render() {
    const redirectTo = this.props.redirectTo;
    if (redirectTo) {
      return <Redirect to={redirectTo} />;
    }
    return null;
  }
}

class DisplayNotificationMessage extends React.PureComponent {
  reset = (event) => {
    store.notificationMessage = null;
  };

  render() {
    const { message } = this.props;
    if (!message) {
      return null;
    }
    let className = "notification";
    if (message.success) {
      className += " is-success";
    } else if (message.warning) {
      className += " is-warning";
    } else {
      className += " is-info";
    }
    return (
      <div className={className}>
        <button className="delete" onClick={this.reset} />
        {message.message}
      </div>
    );
  }
}
