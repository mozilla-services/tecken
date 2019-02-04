import React, { PureComponent } from "react";
import { Link } from "react-router-dom";

import { isBefore, formatDistanceStrict } from "date-fns";

import {
  parseISODate,
  Loading,
  filterToQueryString,
  parseQueryString
} from "./Common";
import Fetch from "./Fetch";
import store from "./Store";

class Tokens extends PureComponent {
  constructor(props) {
    super(props);
    this.pageTitle = "API Tokens";
    this.state = {
      loading: true, // undone by componentDidMount
      tokens: null,
      totals: {},
      permissions: null,
      filter: {}
    };
  }

  componentWillMount() {
    store.resetApiRequests();
  }

  componentDidMount() {
    document.title = this.pageTitle;

    if (this.props.location.search) {
      this.setState(
        { filter: parseQueryString(this.props.location.search) },
        () => {
          this._fetchTokens();
        }
      );
    } else {
      this._fetchTokens();
    }
  }

  _fetchTokens = () => {
    this.setState({ loading: true });

    let url = "/api/tokens/";
    const qs = filterToQueryString(this.state.filter);
    if (qs) {
      url += "?" + qs;
    }
    this.props.history.push({ search: qs });

    Fetch(url, { credentials: "same-origin" }).then(r => {
      if (r.status === 403 && !store.currentUser) {
        store.setRedirectTo(
          "/",
          `You have to be signed in to view "${this.pageTitle}"`
        );
        return;
      }
      this.setState({ loading: false });
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null;
        }
        return r.json().then(response => {
          this.setState({
            tokens: response.tokens,
            totals: response.totals,
            permissions: response.permissions
          });
        });
      } else {
        store.fetchError = r;
      }
    });
  };

  updateFilter = newFilters => {
    this.setState(
      {
        filter: Object.assign({}, this.state.filter, newFilters)
      },
      this._fetchTokens
    );
  };

  deleteToken = id => {
    Fetch(`/api/tokens/token/${id}`, {
      method: "DELETE",
      credentials: "same-origin"
    }).then(r => {
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null;
        }
        store.setNotificationMessage("API Token deleted");
        this._fetchTokens();
      } else {
        store.fetchError = r;
      }
    });
  };

  extendToken = (id, days = null) => {
    const formData = new FormData();
    formData.append("days", days);
    return Fetch(`/api/tokens/token/${id}/extend`, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
      headers: new Headers({
        "X-CSRFToken": this.props.csrfToken
      })
    }).then(r => {
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null;
        }
        return r.json().then(response => {
          store.setNotificationMessage(
            `API Token extended ${response.days} days`
          );
          return this._fetchTokens();
        });
      } else {
        store.fetchError = r;
      }
    });
  };

  render() {
    return (
      <div>
        {this.state.loading && <Loading />}

        {this.state.permissions && !this.state.permissions.length ? (
          <article className="message is-warning">
            <div className="message-header">
              <p>Warning</p>
            </div>
            <div className="message-body">
              <p>
                You do <b>not have any permissions</b>. It means you{" "}
                <b>can not create any API tokens</b>.
              </p>
              <p>
                To get permission(s) you need to be promoted by an administrator
                to elevate your access privileges. <br />
                <Link to="/help">Go to Help</Link>
              </p>
            </div>
          </article>
        ) : null}

        {this.state.tokens ? (
          <div>
            <h2 className="title">Your API Tokens</h2>
            <DisplayTokens
              tokens={this.state.tokens}
              totals={this.state.totals}
              filter={this.state.filter}
              deleteToken={this.deleteToken}
              extendToken={this.extendToken}
              updateFilter={this.updateFilter}
            />
          </div>
        ) : null}

        {this.state.permissions && this.state.permissions.length ? (
          <div>
            <hr />
            <h2 className="title">Create new API Token</h2>
            <CreateTokenForm
              permissions={this.state.permissions}
              createToken={this.createToken}
              refreshTokens={this._fetchTokens}
            />
          </div>
        ) : null}
      </div>
    );
  }
}

export default Tokens;

class CreateTokenForm extends PureComponent {
  state = {
    loading: false,
    validationErrors: null
  };
  submitCreate = event => {
    event.preventDefault();
    const expires = this.refs.expires.value;
    const notes = this.refs.notes.value;
    const permissions = [];
    [...this.refs.permissions.options].forEach(option => {
      if (option.selected) {
        permissions.push(option.value);
      }
    });
    this.setState({ loading: true });
    const formData = new FormData();
    formData.append("permissions", permissions);
    formData.append("expires", expires);
    formData.append("notes", notes.trim());
    return Fetch("/api/tokens/", {
      method: "POST",
      body: formData,
      credentials: "same-origin"
    }).then(r => {
      this.setState({ loading: false });
      if (store.fetchError) {
        store.fetchError = null;
      }
      if (r.status === 201) {
        this.setState({ validationErrors: null });
        this._resetForm();
        store.setNotificationMessage("New API Token created");
        this.props.refreshTokens();
        // Scroll up to the top to see the notification message
        // and the new entry in the table.
        setTimeout(() => {
          window.scroll(0, 0);
        });
      } else if (r.status === 400) {
        r.json().then(data => {
          this.setState({ validationErrors: data.errors });
        });
      } else {
        store.fetchError = r;
      }
    });
  };

  _resetForm = () => {
    this.refs.notes.value = "";
  };

  render() {
    let validationErrors = this.state.validationErrors;
    if (validationErrors === null) {
      // makes it easier to reference in the JSX
      validationErrors = {};
    }

    const permissionNames = this.props.permissions.map(p => p.name);
    const hasBothUploadPermissions =
      permissionNames.includes("Upload Symbols Files") &&
      permissionNames.includes("Upload Try Symbols Files");

    return (
      <form onSubmit={this.submitCreate}>
        <div className="field">
          <label className="label">Permissions</label>
          <div className="select is-multiple">
            <select
              multiple={true}
              className={validationErrors.permissions ? "is-danger" : ""}
              ref="permissions"
              size={this.props.permissions.length}
            >
              {this.props.permissions.map(permission => {
                return (
                  <option key={permission.id} value={permission.id}>
                    {permission.name}
                  </option>
                );
              })}
            </select>
          </div>
          {validationErrors.permissions ? (
            <p className="help is-danger">{validationErrors.permissions[0]}</p>
          ) : null}
        </div>
        <div className="field">
          <label className="label">Expires</label>
          <p className="control">
            <span className="select">
              <select
                ref="expires"
                defaultValue={365}
                className={validationErrors.expires ? "is-danger" : ""}
              >
                <option value={1}>1 day</option>
                <option value={7}>1 week</option>
                <option value={30}>1 month</option>
                <option value={365}>1 year</option>
                <option value={365 * 10}>10 years</option>
              </select>
            </span>
          </p>
          {validationErrors.expires ? (
            <p className="help is-danger">{validationErrors.expires[0]}</p>
          ) : null}
        </div>
        <div className="field">
          <label className="label">Notes</label>
          <p className="control">
            <textarea
              ref="notes"
              placeholder="optional notes..."
              className={
                validationErrors.notes ? "textarea is-danger" : "textarea"
              }
            />
          </p>
          {validationErrors.notes ? (
            <p className="help is-danger">{validationErrors.notes[0]}</p>
          ) : null}
        </div>
        <div className="field is-grouped">
          <p className="control">
            <button
              type="submit"
              className={
                this.state.loading
                  ? "button is-primary is-loading"
                  : "button is-primary"
              }
            >
              Create
            </button>
          </p>
        </div>

        {hasBothUploadPermissions ? (
          <p>
            <b>Note!</b> An API Token can not contain <i>both</i> the{" "}
            <code>Upload Symbols Files</code> <i>and</i>
            <code>Upload Try Symbols Files</code>.
          </p>
        ) : null}
      </form>
    );
  }
}

class DisplayTokens extends PureComponent {
  state = {
    extend: null
  };
  onDelete = (event, id, expired) => {
    event.preventDefault();
    if (expired || window.confirm("Are you sure?")) {
      this.props.deleteToken(id);
    }
  };

  filterOnAll = event => {
    event.preventDefault();
    const filter = this.props.filter;
    filter.state = "all";
    this.props.updateFilter(filter);
  };

  filterOnActive = event => {
    event.preventDefault();
    const filter = this.props.filter;
    delete filter.state;
    this.props.updateFilter(filter);
  };

  filterOnExpired = event => {
    event.preventDefault();
    const filter = this.props.filter;
    filter.state = "expired";
    this.props.updateFilter(filter);
  };

  render() {
    const { tokens, totals, filter } = this.props;
    return (
      <div>
        <div className="tabs is-centered">
          <ul>
            <li className={!filter.state ? "is-active" : ""}>
              <Link to="/tokens?state=active" onClick={this.filterOnActive}>
                Active ({totals.active})
              </Link>
            </li>
            <li className={filter.state === "all" ? "is-active" : ""}>
              <Link to="/tokens" onClick={this.filterOnAll}>
                All ({totals.all})
              </Link>
            </li>
            <li className={filter.state === "expired" ? "is-active" : ""}>
              <Link to="/tokens?state=expired" onClick={this.filterOnExpired}>
                Expired ({totals.expired})
              </Link>
            </li>
          </ul>
        </div>
        <table className="table is-fullwidth">
          <thead>
            <tr>
              <th style={{ width: 380 }}>Key</th>
              <th>Expires</th>
              <th>Permissions</th>
              <th>Notes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map(token => {
              return (
                <tr key={token.id}>
                  <td>
                    <DisplayKey tokenKey={token.key} />
                  </td>
                  <td>
                    <DisplayExpires expires={token.expires_at} />{" "}
                    {token.is_expired && (
                      <span className="tag is-danger">Expired</span>
                    )}
                  </td>
                  <td>
                    {token.permissions.map(p => (
                      <code key={p.id} style={{ display: "block" }}>
                        {p.name}
                      </code>
                    ))}
                  </td>
                  <td style={{ maxWidth: 450 }}>{token.notes}</td>
                  <td>
                    {!this.state.extend || this.state.extend !== token.id ? (
                      <button
                        type="button"
                        className="button is-danger is-small"
                        onClick={event =>
                          this.onDelete(event, token.id, token.is_expired)
                        }
                      >
                        Delete
                      </button>
                    ) : null}{" "}
                    {this.state.extend && this.state.extend === token.id ? (
                      <ExtendForm
                        onSubmit={days => {
                          this.props.extendToken(token.id, days).then(() => {
                            this.setState({ extend: null });
                          });
                        }}
                        onCancel={() => {
                          this.setState({ extend: null });
                        }}
                      />
                    ) : (
                      <button
                        type="button"
                        className="button is-warning is-small"
                        title="Extend when this token expires"
                        onClick={() => this.setState({ extend: token.id })}
                      >
                        Extend
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }
}

class ExtendForm extends React.PureComponent {
  state = {
    loading: false
  };
  onSubmit = event => {
    event.preventDefault();
    this.setState({ loading: true }, () => {
      this.props.onSubmit(this.refs.days.value);
    });
  };
  render() {
    return (
      <form onSubmit={this.onSubmit}>
        <span className="select">
          <select ref="days" defaultValue={365}>
            <option value={1}>1 day</option>
            <option value={7}>1 week</option>
            <option value={30}>1 month</option>
            <option value={365}>1 year</option>
            <option value={365 * 10}>10 years</option>
          </select>
        </span>{" "}
        <button
          type="submit"
          className={
            this.state.loading
              ? "button is-small is-primary is-loading"
              : "button is-small is-primary"
          }
        >
          Extend
        </button>{" "}
        {!this.state.loading ? (
          <button
            type="button"
            className="button is-small"
            onClick={event => {
              this.props.onCancel();
            }}
          >
            Cancel
          </button>
        ) : null}
      </form>
    );
  }
}

class DisplayKey extends PureComponent {
  state = { truncate: true };
  toggle = event => {
    this.setState({ truncate: !this.state.truncate });
  };
  render() {
    let code = <code>{this.props.tokenKey}</code>;
    if (this.state.truncate) {
      const truncated = this.props.tokenKey.substr(0, 10);
      code = <code>{`${truncated}…`}</code>;
    }

    return (
      <p>
        {code}
        <span
          title="Click to toggle displaying the whole key"
          className="button is-small"
          onClick={this.toggle}
        >
          <span className="icon is-small">
            <i
              className={
                this.state.truncate ? "fa fa-expand" : "fa fa-compress"
              }
            />
          </span>
        </span>
      </p>
    );
  }
}

const DisplayExpires = ({ expires }) => {
  const date = parseISODate(expires);
  const now = new Date();
  if (isBefore(date, now)) {
    return (
      <span className="token-expired" title={expires}>
        {formatDistanceStrict(date, now)} ago
      </span>
    );
  } else {
    return <span title={expires}>in {formatDistanceStrict(date, now)}</span>;
  }
};
