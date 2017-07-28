import React, { Component } from 'react'
import './App.css'
import {
  BrowserRouter as Router,
  Route,
  NavLink,
  Redirect
} from 'react-router-dom'
import { observer } from 'mobx-react'
import 'bulma/css/bulma.css'

import Home from './Home'
import Help from './Help'
import Tokens from './Tokens'
import Uploads from './Uploads'
import Upload from './Upload'
import Files from './Files'
import Users from './Users'
import User from './User'
import FetchError from './FetchError'
import Fetch from './Fetch'
import DisplayAPIRequests from './APIRequests'
import store from './Store'

const App = observer(
  class App extends Component {
    constructor(props) {
      super(props)
      this.state = {
        redirectTo: null
      }
    }

    componentWillMount() {
      Fetch('/api/auth/', { credentials: 'same-origin' }).then(r => {
        if (r.status === 200) {
          if (store.fetchError) {
            store.fetchError = null
          }
          r.json().then(response => {
            if (response.user) {
              store.currentUser = response.user
              store.signOutUrl = response.sign_out_url
              // XXX do with the ?signedin=true in the query string?
            } else {
              store.signInUrl = response.sign_in_url
            }
          })
        } else {
          store.fetchError = r
        }
      })
    }

    signIn = event => {
      event.preventDefault()
      let url = store.signInUrl
      /* When doing local development, the Django runserver is
         running at 'http://web:8000', in Docker, as far as the React dev
         server is concerned. That doesn't work outside Docker
         (i.e on the host) so we'll replace this.
         It's safe since the string replace is hardcoded and only does
         something if the original URL matched.
         */
      url = url.replace('http://web:8000/', 'http://localhost:8000/')
      document.location.href = url
    }

    signOut = event => {
      event.preventDefault()
      let url = store.signOutUrl
      // See above explanation, in 'signIn()' about this "hack"
      url = url.replace('http://web:8000/', 'http://localhost:3000/')
      Fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        redirect: 'manual'
      }).then(r => {
        store.setRedirectTo('/', {
          message: 'Signed out',
          success: true
        })
      })
    }

    render() {
      // The reason we make this conditional first, rather than letting
      // RedirectMaybe be its own observer, is that this way we can
      // *immediately* do an "early exit" if it's set to something.
      if (store.redirectTo) {
        return (
          <Router>
            <RedirectMaybe redirectTo={store.redirectTo} />
          </Router>
        )
      }
      return (
        <Router>
          <div>
            <nav className="nav has-shadow" id="top">
              <div className="container">
                <div className="nav-left">
                  <a className="nav-item" href="/">
                    Mozilla Symbol Server
                  </a>
                </div>
                <span className="nav-toggle">
                  <span />
                  <span />
                  <span />
                </span>
                <div className="nav-right nav-menu">
                  <NavLink
                    to="/"
                    exact
                    className="nav-item is-tab"
                    activeClassName="is-active"
                  >
                    Home
                  </NavLink>
                  {store.currentUser && store.currentUser.is_superuser
                    ? <NavLink
                        to="/users"
                        className="nav-item is-tab"
                        activeClassName="is-active"
                      >
                        User Management
                      </NavLink>
                    : null}
                  {store.currentUser &&
                    <NavLink
                      to="/tokens"
                      className="nav-item is-tab"
                      activeClassName="is-active"
                    >
                      API Tokens
                    </NavLink>}
                  {store.currentUser &&
                    <NavLink
                      to="/uploads"
                      className="nav-item is-tab"
                      activeClassName="is-active"
                    >
                      Uploads
                    </NavLink>}
                  <NavLink
                    to="/help"
                    className="nav-item is-tab"
                    activeClassName="is-active"
                  >
                    Help
                  </NavLink>
                  <span className="nav-item">
                    {store.currentUser
                      ? <button
                          onClick={this.signOut}
                          className="button is-info"
                          title={`Signed in as ${store.currentUser.email}`}
                        >
                          Sign Out
                        </button>
                      : <button
                          onClick={this.signIn}
                          className="button is-info"
                        >
                          Sign In
                        </button>}
                  </span>
                </div>
              </div>
            </nav>
            <section className="section">
              <div className="container">
                <DisplayNotificationMessage
                  message={store.notificationMessage}
                />
                <FetchError error={store.fetchError} />
                <Route
                  path="/"
                  exact
                  render={props =>
                    <Home
                      {...props}
                      signIn={this.signIn}
                      signOut={this.signOut}
                    />}
                />
                <Route path="/help" component={Help} />
                <Route path="/tokens" component={Tokens} />
                <Route path="/uploads/files" exact component={Files} />
                <Route path="/uploads/upload/:id" component={Upload} />
                <Route path="/uploads" exact component={Uploads} />
                <Route path="/users/:id" component={User} />
                <Route path="/users" exact component={Users} />

                <DisplayAPIRequests />
              </div>
            </section>
            <footer className="footer">
              <div className="container">
                <div className="content has-text-centered">
                  <p>
                    <strong>The Mozilla Symbol Server</strong>
                    <br />
                    Powered by{' '}
                    <a
                      href="https://github.com/mozilla-services/tecken"
                      rel="noopener noreferrer"
                    >
                      Tecken
                    </a>
                    {' • '}
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
          </div>
        </Router>
      )
    }
  }
)

export default App

class RedirectMaybe extends Component {
  componentDidMount() {
    if (this.props.redirectTo) {
      // tell the store we've used it
      store.redirectTo = null
    }
  }
  render() {
    const redirectTo = this.props.redirectTo
    if (redirectTo) {
      return <Redirect to={redirectTo} />
    }
    return null
  }
}

class DisplayNotificationMessage extends Component {
  reset = event => {
    store.notificationMessage = null
  }

  render() {
    const { message } = this.props
    if (!message) {
      return null
    }
    let className = 'notification'
    if (message.success) {
      className += ' is-success'
    } else if (message.warning) {
      className += ' is-warning'
    } else {
      className += ' is-info'
    }
    return (
      <div className={className}>
        <button className="delete" onClick={this.reset} />
        {message.message}
      </div>
    )
  }
}
