import React, { Component } from 'react'
import { Link } from 'react-router-dom'

import { toDate, isBefore, formatDistanceStrict } from 'date-fns/esm'

import { Loading, FetchError } from './Common'
import './Tokens.css'

class Tokens extends Component {
  constructor(props) {
    super(props)
    this.state = {
      loading: true, // done by componentDidMount
      fetchError: null,
      tokens: null,
      permissions: null
    }
  }
  componentDidMount() {
    document.title = 'API Tokens'

    this._fetchTokens()
  }

  _fetchTokens = () => {
    fetch('/api/tokens/', { credentials: 'same-origin' }).then(r => {
      this.setState({ loading: false })
      if (r.status === 200) {
        return r.json().then(response => {
          this.setState({
            fetchError: null,
            tokens: response.tokens,
            permissions: response.permissions
          })
        })
      } else {
        this.setState({ fetchError: r })
      }
    })
  }

  createToken = (permissions, expires, notes) => {
    this.setState({ loading: true })
    const formData = new FormData()
    formData.append('permissions', permissions)
    formData.append('expires', expires)
    formData.append('notes', notes.trim())
    fetch('/api/tokens/', {
      method: 'POST',
      body: formData,
      credentials: 'same-origin'
    }).then(r => {
      this.setState({ loading: false })
      if (r.status === 201) {
        this._fetchTokens()
      } else {
        this.setState({ fetchError: r })
      }
    })
  }


  deleteToken = (id) => {
    fetch(`/api/tokens/${id}`, {
      method: 'DELETE',
      credentials: 'same-origin'
    }).then(r => {
      if (r.status === 200) {
        this._fetchTokens()
      } else {
        this.setState({ fetchError: r })
      }
    })
  }

  render() {
    return (
      <div>
        <h1 className="title">API Tokens</h1>
        {this.state.loading ? <Loading /> : null}
        {this.state.fetchError
          ? <FetchError error={this.state.fetchError} />
          : null}

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

        {!this.state.loading &&
        this.state.permissions &&
        this.state.permissions.length
          ? <div>
              <hr />
              <h2 className="title">Create new API Token</h2>
              <CreateTokenForm
                permissions={this.state.permissions}
                createToken={this.createToken}
              />
            </div>
          : null}
      </div>
    )
  }
}

export default Tokens

class CreateTokenForm extends Component {
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
    this.props.createToken(permissions, expires, notes)
  }
  render() {
    return (
      <form onSubmit={this.submitCreate}>
        <div className="field">
          <label className="label">Permissions</label>
          <p className="control">
            <select
              multiple={true}
              className="multi-select"
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
          </p>
        </div>
        <div className="field">
          <label className="label">Expires</label>
          <p className="control">
            <span className="select">
              <select ref="expires" defaultValue={365}>
                <option value={1}>1 day</option>
                <option value={7}>1 week</option>
                <option value={30}>1 month</option>
                <option value={365}>1 year</option>
                <option value={365 * 10}>10 years</option>
              </select>
            </span>
          </p>
        </div>
        <div className="field">
          <label className="label">Notes</label>
          <p className="control">
            <textarea ref="notes" className="textarea" placeholder="" />
          </p>
        </div>
        <div className="field is-grouped">
          <p className="control">
            <button type="submit" className="button is-primary">
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
    return (
      <table className="table">
        <thead>
          <tr>
            <th>Key</th>
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
                  <DisplayExpires expires={token.expires_at}/>
                </td>
                <td>
                  {token.permissions.map(p =>
                    <code key={p.id} style={{display: 'block'}}>
                      {p.name}
                    </code>
                  )}
                </td>
                <td style={{maxWidth: 250}}>
                  {token.notes}
                </td>
                <td>
                  <button
                    type="button"
                    className="button is-danger"
                    onClick={event => this.onDelete(event, token.id, token.is_expired)}
                    >Delete</button>
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
    if (this.state.truncate) {
      const truncated = this.props.tokenKey.substr(0, 10)
      return (
        <code
          onClick={this.toggle}
          title="Click to see the whole thing"
        >{`${truncated}…`}</code>
      )
    } else {
      return (
        <code>
          {this.props.tokenKey}
        </code>
      )
    }
  }
}


const DisplayExpires = ({ expires }) => {
  const date = toDate(expires)
  const now = new Date()
  if (isBefore(date, now)) {
    return <span
      className="token-expired">{formatDistanceStrict(date, now)} ago</span>
  } else {
    return <span>in {formatDistanceStrict(date, now)}</span>

  }
}
