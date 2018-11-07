import React from "react";
import { NavLink, Link } from "react-router-dom";
import { observer } from "mobx-react";
import "./Nav.css";
import store from "./Store";

const Nav = observer(
  class Nav extends React.Component {
    constructor(props) {
      super(props);

      this.state = {
        menuToggled: true
      };
    }

    toggleMenu = event => {
      event.preventDefault();
      this.setState({ menuToggled: !this.state.menuToggled });
    };

    render() {
      return (
        <nav className="navbar has-shadow" id="top">
          <div className="navbar-brand">
            <Link className="navbar-item" to="/">
              Mozilla Symbol Server
            </Link>

            <div
              data-target="navMenubd-example"
              className={
                this.state.menuToggled
                  ? "navbar-burger"
                  : "navbar-burger is-active"
              }
              onClick={this.toggleMenu}
            >
              <span />
              <span />
              <span />
            </div>
          </div>

          <div
            id="navMenubd-example"
            className={
              this.state.menuToggled ? "navbar-menu" : "navbar-menu is-active"
            }
          >
            <div className="navbar-end">
              <NavLink
                to="/"
                exact
                className="navbar-item"
                activeClassName="is-active"
              >
                Home
              </NavLink>
              <NavLink
                to="/downloads"
                exact
                className="navbar-item"
                activeClassName="is-active"
              >
                Downloads
              </NavLink>
              {store.currentUser && store.currentUser.is_superuser ? (
                <NavLink
                  to="/users"
                  className="navbar-item"
                  activeClassName="is-active"
                >
                  User Management
                </NavLink>
              ) : null}
              {store.currentUser &&
                store.hasPermission("tokens.manage_tokens") && (
                  <NavLink
                    to="/tokens"
                    className="navbar-item"
                    activeClassName="is-active"
                  >
                    API Tokens
                  </NavLink>
                )}
              {store.currentUser &&
                store.hasPermission("upload.upload_symbols") && (
                  <NavLink
                    to="/uploads"
                    className="navbar-item"
                    activeClassName="is-active"
                  >
                    Uploads
                  </NavLink>
                )}
              <NavLink
                to="/symbolication"
                className="navbar-item"
                activeClassName="is-active"
              >
                Symbolication
              </NavLink>
              <NavLink
                to="/help"
                className="navbar-item"
                activeClassName="is-active"
              >
                Help
              </NavLink>
              <span className="navbar-item">
                {store.currentUser && (
                  <button
                    onClick={this.props.signOut}
                    className="button is-info"
                    title={`Signed in as ${store.currentUser.email}`}
                  >
                    Sign Out
                  </button>
                )}
                {!store.currentUser && store.signInUrl && (
                  <button
                    onClick={this.props.signIn}
                    className="button is-info"
                  >
                    Sign In
                  </button>
                )}
              </span>
            </div>
          </div>
        </nav>
      );
    }
  }
);

export default Nav;
