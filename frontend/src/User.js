import React, { Component } from 'react'
import { Redirect, Link } from 'react-router-dom'

import { Loading } from './Common'
import Fetch from './Fetch'
import store from './Store'

export default class User extends Component {
  constructor(props) {
    super(props)
    this.pageTitle = 'User Management'
    this.state = {
      loading: true,
      user: null,
      groups: null,
      redirectTo: null
    }
  }
  componentWillMount() {
    store.resetApiRequests()
  }

  componentDidMount() {
    document.title = this.pageTitle
    this._fetchUser(this.props.match.params.id)
  }

  _fetchUser = id => {
    this.setState({ loading: true })
    Fetch(`/api/users/${id}`, { credentials: 'same-origin' }).then(r => {
      this.setState({ loading: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            user: response.user,
            groups: response.groups,
            loading: false
          })
        })
      } else {
        store.fetchError = r
        // this.setState({ fetchError: r })
      }
    })
  }

  goBack = () => {
    this.setState({
      redirectTo: {
        pathname: '/users'
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
        {this.state.loading && <Loading />}
        {this.state.user &&
          <EditUserForm
            user={this.state.user}
            groups={this.state.groups}
            editUser={this.editUser}
            userSaved={this.goBack}
          />}
        <hr />
        {this.state.groups && <ExplainGroups groups={this.state.groups} />}
      </div>
    )
  }
}

class EditUserForm extends Component {
  state = {
    loading: false,
    validationErrors: null
  }
  componentWillUnmount() {
    this.dismounted = true
  }
  submitForm = event => {
    event.preventDefault()
    const groups = []
    ;[...this.refs.groups.options].forEach(option => {
      if (option.selected) {
        groups.push(option.value)
      }
    })
    const isActive = this.refs.active.checked
    const isSuperuser = this.refs.superuser.checked

    this.setState({ loading: true })
    const formData = new FormData()
    formData.append('groups', groups)
    formData.append('is_active', isActive)
    formData.append('is_superuser', isSuperuser)
    return fetch(`/api/users/${this.props.user.id}`, {
      method: 'POST',
      body: formData,
      credentials: 'same-origin'
    }).then(r => {
      if (store.fetchError) {
        store.fetchError = null
      }
      if (r.status === 200) {
        this.setState({ loading: false, validationErrors: null })
        // this._resetForm()
        this.props.userSaved(this.props.user.id)
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

    const { user, groups } = this.props
    const userGroupIds = user.groups.map(group => group.id)

    return (
      <form onSubmit={this.submitForm}>
        <div className="field">
          <label className="label">Groups</label>
          <div className="select is-multiple">
            <select
              multiple={true}
              className={validationErrors.permissions ? 'is-danger' : ''}
              ref="groups"
              size={groups.length}
              defaultValue={userGroupIds}
            >
              {this.props.groups.map(group => {
                return (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                )
              })}
            </select>
          </div>
          {validationErrors.groups
            ? <p className="help is-danger">
                {validationErrors.groups[0]}
              </p>
            : null}
        </div>
        <div className="field">
          <label className="checkbox">
            <input
              type="checkbox"
              name="is_active"
              ref="active"
              defaultChecked={user.is_active}
            />{' '}
            Active
          </label>
        </div>
        <div className="field">
          <label className="checkbox">
            <input
              type="checkbox"
              name="is_superuser"
              ref="superuser"
              defaultChecked={user.is_superuser}
            />{' '}
            Superuser
          </label>
        </div>
        <div className="field is-grouped">
          <div className="control">
            <button
              type="submit"
              className={
                this.state.loading
                  ? 'button is-primary is-loading'
                  : 'button is-primary'
              }
            >
              Save
            </button>
          </div>
          <div className="control">
            <Link to="/users" className="button is-link">
              Cancel
            </Link>
          </div>
        </div>
      </form>
    )
  }
}

const ExplainGroups = ({ groups }) => {
  return (
    <div className="container">
      <h1 className="title">Groups</h1>
      <p>
        Every action requires a <b>permission</b> but to give users permissions,
        this is done by putting the user in <b>groups</b> that <i>contain</i>{' '}
        permissions.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th>Group Name</th>
            <th>Permissions</th>
          </tr>
        </thead>
        <tbody>
          {groups.map(group => {
            return (
              <tr key={group.id}>
                <td>
                  {group.name}
                </td>
                <td>
                  <ul style={{ marginTop: 0 }}>
                    {group.permissions.map(p =>
                      <li key={p.id}>
                        {p.name}
                      </li>
                    )}
                  </ul>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
