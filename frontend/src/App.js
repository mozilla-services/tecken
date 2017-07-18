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

import store from './Store'

const App = observer(
  class App extends Component {
    constructor(props) {
      super(props)
      this.state = {
        redirectTo: null
      }
    }
    componentDidMount() {
      fetch('/api/auth/', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(response => {
          // console.log('RESPONSE', response)
          if (response.user) {
            store.currentUser = response.user.email
            store.signOutUrl = response.sign_out_url
            // XXX do we need to remove the ?signedin=True in the query string?
          }
        })
    }

    signIn = event => {
      event.preventDefault()
      fetch('/api/auth/', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(response => {
          if (response.sign_in_url) {
            document.location.href = response.sign_in_url
          } else {
            store.currentUser = response.user.email
            store.signOutUrl = response.sign_out_url
          }
        })
    }

    signOut = event => {
      event.preventDefault()
      fetch(store.signOutUrl, {
        method: 'POST',
        credentials: 'same-origin'
      }).then(r => {
        console.log('SIGNED OUT:')
        console.log(r)
      })
    }

    render() {
      if (this.state.redirectTo) {
        return <Redirect to={this.state.redirectTo} />
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
                  <NavLink to="/" exact className="nav-item is-tab" activeClassName="is-active">
                    Home
                  </NavLink>
                  <NavLink to="/tokens" className="nav-item is-tab" activeClassName="is-active">
                    API Tokens
                  </NavLink>
                  <NavLink to="/uploads" className="nav-item is-tab" activeClassName="is-active">
                    Uploads
                  </NavLink>
                  <NavLink to="/help" className="nav-item is-tab" activeClassName="is-active">
                    Help
                  </NavLink>
                  <span className="nav-item">
                    {store.currentUser
                      ? <a onClick={this.signOut} className="button is-info">
                          Sign Out
                        </a>
                      : <a onClick={this.signIn} className="button is-info">
                          Sign In
                        </a>}
                  </span>
                </div>
              </div>
            </nav>
            <section className="section">
              <div className="container content">
                <Route path="/" exact component={Home} />
                <Route path="/help" component={Help} />
                <Route path="/tokens" component={Tokens} />
                <Route path="/uploads" component={Uploads} />
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
