import React, { Component } from 'react'
import { Link } from 'react-router-dom'

import { toDate, isBefore, formatDistanceStrict } from 'date-fns/esm'

import { Loading } from './Common'
import Fetch from './Fetch'
import store from './Store'

class Tokens extends Component {
  constructor(props) {
    super(props)
    this.pageTitle = 'API Tokens'
    this.state = {
      loading: true, // undone by componentDidMount
      tokens: null,
      permissions: null
    }
  }

  componentWillMount() {
    store.resetApiRequests()
  }

  componentDidMount() {
    document.title = this.pageTitle
    this._fetchTokens()
  }

  _fetchTokens = () => {
    this.setState({ loading: true })
    Fetch('/api/tokens/', { credentials: 'same-origin' }).then(r => {
      this.setState({ loading: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            tokens: response.tokens,
            permissions: response.permissions
          })
        })
      } else {
        store.fetchError = r
        // this.setState({ fetchError: r })
      }
    })
  }

  deleteToken = id => {
    Fetch(`/api/tokens/${id}`, {
      method: 'DELETE',
      credentials: 'same-origin'
    }).then(r => {
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        this._fetchTokens()
      } else {
        store.fetchError = r
        // this.setState({ fetchError: r })
      }
    })
  }

  render() {
    return (
      <div>
        <h1 className="title">
          {this.pageTitle}
        </h1>
        {this.state.loading && <Loading />}

        {this.state.permissions && !this.state.permissions.length
          ? <article className="message is-warning">
              <div className="message-header">
                <p>Warning</p>
                {/* <button className="delete"></button> */}
              </div>
              <div className="message-body">
                <p>
                  You do <b>not have any permissions</b>. It means you{' '}
                  <b>can not create any API tokens</b>.
                </p>
                <p>
                  To get permission(s) you need to be promoted by an
                  administrator to elevate your access privileges. <br />
                  <Link to="/help">Go to Help</Link>
                </p>
              </div>
            </article>
          : null}

        {this.state.tokens
          ? <div>
              <h2 className="title">Your API Tokens</h2>
              <DisplayTokens
                tokens={this.state.tokens}
                deleteToken={this.deleteToken}
              />
            </div>
          : null}

        {this.state.permissions && this.state.permissions.length
          ? <div>
              <hr />
              <h2 className="title">Create new API Token</h2>
              <CreateTokenForm
                permissions={this.state.permissions}
                createToken={this.createToken}
                refreshTokens={this._fetchTokens}
              />
            </div>
          : null}
      </div>
    )
  }
}

export default Tokens

class CreateTokenForm extends Component {
  state = {
    loading: false,
    validationErrors: null
  }
  componentWillUnmount() {
    this.dismounted = true
  }
  submitCreate = event => {
    event.preventDefault()
    const expires = this.refs.expires.value
    const notes = this.refs.notes.value
    const permissions = []
    ;[...this.refs.permissions.options].forEach(option => {
      if (option.selected) {
        permissions.push(option.value)
      }
    })
    this.setState({ loading: true })
    const formData = new FormData()
    formData.append('permissions', permissions)
    formData.append('expires', expires)
    formData.append('notes', notes.trim())
    return Fetch('/api/tokens/', {
      method: 'POST',
      body: formData,
      credentials: 'same-origin'
    }).then(r => {
      if (store.fetchError) {
        store.fetchError = null
      }
      if (r.status === 201) {
        this.setState({ loading: false, validationErrors: null })
        this._resetForm()
        this.props.refreshTokens()
      } else if (r.status === 400) {
        r.json().then(data => {
          this.setState({ loading: false, validationErrors: data.errors })
        })
      } else {
        // this.setState({ fetchError: r })
        store.fetchError = r
      }
    })
  }

  _resetForm = () => {
    this.refs.notes.value = ''
  }

  render() {
    let validationErrors = this.state.validationErrors
    if (validationErrors === null) {
      // makes it easier to reference in the JSX
      validationErrors = {}
    }
    return (
      <form onSubmit={this.submitCreate}>
        <div className="field">
          <label className="label">Permissions</label>
          <div className="select select-multiple">
            <select
              multiple={true}
              className={validationErrors.permissions ? 'is-danger' : ''}
              ref="permissions"
              size={this.props.permissions.length}
            >
              {this.props.permissions.map(permission => {
                return (
                  <option key={permission.id} value={permission.id}>
                    {permission.name}
                  </option>
                )
              })}
            </select>
          </div>
          {validationErrors.permissions
            ? <p className="help is-danger">
                {validationErrors.permissions[0]}
              </p>
            : null}
        </div>
        <div className="field">
          <label className="label">Expires</label>
          <p className="control">
            <span className="select">
              <select
                ref="expires"
                defaultValue={365}
                className={validationErrors.expires ? 'is-danger' : ''}
              >
                <option value={1}>1 day</option>
                <option value={7}>1 week</option>
                <option value={30}>1 month</option>
                <option value={365}>1 year</option>
                <option value={365 * 10}>10 years</option>
              </select>
            </span>
          </p>
          {validationErrors.expires
            ? <p className="help is-danger">
                {validationErrors.expires[0]}
              </p>
            : null}
        </div>
        <div className="field">
          <label className="label">Notes</label>
          <p className="control">
            <textarea
              ref="notes"
              placeholder="optional notes..."
              className={
                validationErrors.notes ? 'textarea is-danger' : 'textarea'
              }
            />
          </p>
          {validationErrors.notes
            ? <p className="help is-danger">
                {validationErrors.notes[0]}
              </p>
            : null}
        </div>
        <div className="field is-grouped">
          <p className="control">
            <button
              type="submit"
              className={
                this.state.loading
                  ? 'button is-primary is-loading'
                  : 'button is-primary'
              }
            >
              Create
            </button>
          </p>
        </div>
      </form>
    )
  }
}

class DisplayTokens extends Component {
  onDelete = (event, id, expired) => {
    event.preventDefault()
    if (expired || window.confirm('Are you sure?')) {
      this.props.deleteToken(id)
    }
  }

  render() {
    if (!this.props.tokens.length) {
      return (
        <p>
          You don't have any tokens <b>yet</b>
        </p>
      )
    }
    return (
      <table className="table">
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
          {this.props.tokens.map(token => {
            return (
              <tr key={token.id}>
                <td>
                  <DisplayKey tokenKey={token.key} />
                </td>
                <td>
                  <DisplayExpires expires={token.expires_at} />
                </td>
                <td>
                  {token.permissions.map(p =>
                    <code key={p.id} style={{ display: 'block' }}>
                      {p.name}
                    </code>
                  )}
                </td>
                <td style={{ maxWidth: 250 }}>
                  {token.notes}
                </td>
                <td>
                  <button
                    type="button"
                    className="button is-danger"
                    onClick={event =>
                      this.onDelete(event, token.id, token.is_expired)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }
}

class DisplayKey extends Component {
  state = { truncate: true }
  toggle = event => {
    this.setState({ truncate: !this.state.truncate })
  }
  render() {
    let code = (
      <code>
        {this.props.tokenKey}
      </code>
    )
    if (this.state.truncate) {
      const truncated = this.props.tokenKey.substr(0, 10)
      code = (
        <code>
          {`${truncated}…`}
        </code>
      )
    }

    return (
      <p>
        {code}
        <a
          title="Click to toggle displaying the whole key"
          className="button is-small"
          onClick={this.toggle}
        >
          <span className="icon is-small">
            <i
              className={
                this.state.truncate ? 'fa fa-expand' : 'fa fa-compress'
              }
            />
          </span>
        </a>
      </p>
    )
  }
}

const DisplayExpires = ({ expires }) => {
  const date = toDate(expires)
  const now = new Date()
  if (isBefore(date, now)) {
    return (
      <span className="token-expired">
        {formatDistanceStrict(date, now)} ago
      </span>
    )
  } else {
    return (
      <span>
        in {formatDistanceStrict(date, now)}
      </span>
    )
  }
}
