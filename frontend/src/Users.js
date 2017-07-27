import React, { Component } from 'react'
import { Redirect } from 'react-router-dom'

import { Loading, DisplayDate } from './Common'
import Fetch from './Fetch'
import store from './Store'

class Users extends Component {
  constructor(props) {
    super(props)
    this.pageTitle = 'User Management'
    this.state = {
      loading: true,
      users: null,
      redirectTo: null
    }
  }
  componentWillMount() {
    store.resetApiRequests()
  }

  componentDidMount() {
    document.title = this.pageTitle
    this._fetchUsers()
  }

  _fetchUsers = () => {
    this.setState({ loading: true })
    Fetch('/api/users/', { credentials: 'same-origin' }).then(r => {
      this.setState({ loading: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            users: response.users,
            loading: false
          })
        })
      } else {
        store.fetchError = r
        // this.setState({ fetchError: r })
      }
    })
  }

  editUser = id => {
    this.setState({
      redirectTo: {
        pathname: `/users/${id}`
      }
    })
  }

  render() {
    if (this.state.redirectTo) {
      return <Redirect to={this.state.redirectTo} />
    }
    return (
      <div>
        <h1 className="title">
          {this.pageTitle}
        </h1>
        {this.state.loading
          ? <Loading />
          : <DisplayUsers users={this.state.users} editUser={this.editUser} />}
      </div>
    )
  }
}

export default Users

class DisplayUsers extends Component {
  state = {
    filter: {
      q: ''
    }
  }

  onEdit = (event, id) => {
    event.preventDefault()
    this.props.editUser(id)
  }

  _resetFilter = event => {
    event.preventDefault()
    this.setState({
      filter: {
        q: ''
      }
    })
  }

  render() {
    const { users } = this.props
    if (!users) {
      return (
        <p>
          There are <b>no users</b>.
        </p>
      )
    }
    return (
      <table className="table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Last Login</th>
            <th>Permissions</th>
            <th>Uploads</th>
            <th>API Tokens</th>
            <th />
          </tr>
        </thead>
        <tfoot>
          <tr>
            <th>
              <input
                type="search"
                className="input"
                value={this.state.filter.q}
                onChange={e => this.setState({ filter: { q: e.target.value } })}
                placeholder="Filter by email"
              />
            </th>
            <th />
            <th />
            <th />
            <th />
            <th>
              {this.state.filter.q &&
                <button
                  className="button is-primary"
                  onClick={this._resetFilter}
                >
                  Clear filter
                </button>}
            </th>
          </tr>
        </tfoot>
        <tbody>
          {users.map(user => {
            // Yeah, it's a unscalable hack to filter in render().
            // It's also not scalable to load ALL users into memory with AJAX.
            // There's not even pagination.
            if (this.state.filter.q) {
              // return null if the email doesn't match
              if (
                !user.email
                  .toLowerCase()
                  .includes(this.state.filter.q.toLowerCase())
              ) {
                return null
              }
            }
            return (
              <tr key={user.id}>
                <td>
                  {user.email}{' '}
                  {!user.is_active
                    ? <span className="tag is-danger">Not Active</span>
                    : null}
                </td>
                <td>
                  <DisplayDate date={user.last_login} /> <br />
                  <small>
                    (joined <DisplayDate date={user.date_joined} />)
                  </small>
                </td>
                <td>
                  {user.is_superuser
                    ? <span className="tag is-warning">Superuser</span>
                    : user.permissions.map(p =>
                        <code key={p.id} style={{ display: 'block' }}>
                          {p.name}
                        </code>
                      )}
                </td>
                <td>
                  {user.no_uploads}
                </td>
                <td>
                  {user.no_tokens}
                </td>
                <td>
                  <button
                    type="button"
                    className="button is-info"
                    onClick={event => this.onEdit(event, user.id)}
                  >
                    Edit
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
