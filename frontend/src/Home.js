import React, { Component } from 'react'
import { Link } from 'react-router-dom'
import { observer } from 'mobx-react'

import './Home.css'
import { formatFileSize, Loading } from './Common'
import Fetch from './Fetch'
import store from './Store'

const Home = observer(
  class Home extends Component {
    componentDidMount() {
      document.title = 'Mozilla Symbol Server'
    }

    render() {
      if (store.currentUser) {
        return <SignedInTiles user={store.currentUser} />
      }
      return <AnonymousTiles signIn={this.props.signIn} />
    }
  }
)

export default Home

class SignedInTiles extends Component {
  constructor(props) {
    super(props)
    this.state = {
      loading: true,
      stats: null
    }
  }

  componentDidMount() {
    this._fetchStats()
  }

  _fetchStats = () => {
    this.setState({ loading: true })
    Fetch('/api/_stats/', { credentials: 'same-origin' }).then(r => {
      this.setState({ loading: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            stats: response.stats
          })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  render() {
    const { user } = this.props
    const { stats, loading } = this.state
    return (
      <div>
        <div className="tile is-ancestor">
          <div
            className={
              user.is_superuser ? 'tile is-parent' : 'tile is-parent is-8'
            }
          >
            {store.hasPermission('upload.upload_symbols')
              ? <AboutUploadsTile loading={loading} stats={stats} />
              : <AboutUploadsPermissionTile />}
          </div>
          <div className="tile is-parent">
            {store.hasPermission('tokens.manage_tokens')
              ? <AboutTokensTile loading={loading} stats={stats} />
              : <AboutTokensPermissionTile />}
          </div>
          {user.is_superuser &&
            <div className="tile is-parent">
              <article className="tile is-child box">
                <p className="title">Users</p>
                {loading || !stats
                  ? <Loading />
                  : <p>
                      There <b>{stats.users.total} users</b> in total of which{' '}
                      <b>{stats.users.superusers}</b>{' '}
                      {stats.users.superusers === 1
                        ? 'is superuser'
                        : 'are superusers'},
                      <b>{stats.users.not_active}</b> are inactive.
                    </p>}
                <p>
                  <Link to="/users">
                    Go to <b>User Management</b>
                  </Link>
                </p>
              </article>
            </div>}
        </div>

        <div className="tile is-ancestor">
          <div className="tile is-parent">
            <article className="tile is-child box">
              <p className="title">Authenticated</p>
              <p className="subtitle">
                You are signed in as <b>{user.email}</b>.
                <br />
                {user.is_superuser &&
                  <span>
                    You are a <b>superuser</b>.
                  </span>}
              </p>
              <p style={{ marginTop: 20 }}>
                You have the following permissions:
              </p>
              {user.permissions && user.permissions.length
                ? <ListYourPermissions permissions={user.permissions} />
                : <AboutPermissions />}
            </article>
          </div>
          <div className="tile is-parent is-8">
            <article className="tile is-child box">
              <p className="title">Where do you want to go?</p>
              <p>
                <Link to="/help" className="is-size-5">
                  Help
                </Link>
              </p>
              <p>
                <a
                  href="https://tecken.readthedocs.io"
                  className="is-size-5"
                  rel="noopener noreferrer"
                >
                  Documentation on Readthedocs
                </a>
              </p>
              <p>
                <a
                  href="https://bugzilla.mozilla.org/enter_bug.cgi?product=Socorro&component=Symbols"
                  className="is-size-5"
                  rel="noopener noreferrer"
                >
                  File a bug
                </a>
              </p>
              <p>
                <a
                  href="https://github.com/mozilla-services/tecken"
                  className="is-size-5"
                  rel="noopener noreferrer"
                >
                  Code on GitHub
                </a>
              </p>
            </article>
          </div>
        </div>
      </div>
    )
  }
}

const ListYourPermissions = ({ permissions }) =>
  <ul>
    {permissions.map(perm =>
      <li key={perm.id}>
        <b>
          {perm.name}
        </b>
      </li>
    )}
  </ul>

const AboutPermissions = () =>
  <p>
    <i>None!</i>{' '}
    <a
      href="https://bugzilla.mozilla.org/enter_bug.cgi?product=Socorro&component=Symbols"
      rel="noopener noreferrer"
    >
      File a bug to ask for permissions.
    </a>
    <br />
    <small>Don't forget to mention the email you used to sign in.</small>
  </p>

const AboutUploadsPermissionTile = () =>
  <article className="tile is-child box">
    <p className="title">Uploaded Symbols</p>
    <p>
      <i>You currently don't have permission to upload symbols.</i>
    </p>
  </article>

const AboutUploadsTile = ({ loading, stats }) =>
  <article className="tile is-child box">
    <p className="title">
      {loading || (stats && stats.uploads.all_uploads)
        ? 'Uploaded Symbols'
        : 'Your Uploaded Symbols'}
    </p>
    {loading || !stats
      ? <Loading />
      : <table className="table">
          <thead>
            <tr>
              <th />
              <th>Count</th>
              <th>Total Size</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th>Today</th>
              <td>
                {stats.uploads.today.count}
              </td>
              <td>
                {formatFileSize(stats.uploads.today.total_size)}
              </td>
            </tr>
            <tr>
              <th>Yesterday</th>
              <td>
                {stats.uploads.yesterday.count}
              </td>
              <td>
                {formatFileSize(stats.uploads.yesterday.total_size)}
              </td>
            </tr>
            <tr>
              <th>This Month</th>
              <td>
                {stats.uploads.this_month.count}
              </td>
              <td>
                {formatFileSize(stats.uploads.this_month.total_size)}
              </td>
            </tr>
            <tr>
              <th>This Year</th>
              <td>
                {stats.uploads.this_year.count}
              </td>
              <td>
                {formatFileSize(stats.uploads.this_year.total_size)}
              </td>
            </tr>
          </tbody>
        </table>}
    <Link to="/uploads">
      Go to <b>Uploads</b>
    </Link>
  </article>

const AboutTokensPermissionTile = () =>
  <article className="tile is-child box">
    <p className="title">API Tokens</p>
    <p>
      <i>You currently don't have permission to create API Tokens.</i>
    </p>
  </article>

const AboutTokensTile = ({ loading, stats }) =>
  <article className="tile is-child box">
    <p className="title">API Tokens</p>
    {loading || !stats
      ? <Loading />
      : <p>
          You have <b>{stats.tokens.total} API Tokens</b> of which{' '}
          <b>{stats.tokens.expired}</b> have expired.
        </p>}
    <p>
      <Link to="/tokens">
        Go to <b>API Tokens</b>
      </Link>
    </p>
  </article>

const AnonymousTiles = ({ signIn }) =>
  <div>
    <div className="tile is-ancestor">
      <div className="tile is-parent is-12">
        <article className="tile is-child box">
          <p className="title">
            What is <b>Mozilla Symbol Server</b>?
          </p>
          <div className="content">
            <p>
              A collection of web services dealing with <b>symbol files</b>.
              Uploading them, downloading them and using them to convert C++
              stack traces to signatures.
            </p>
            <p>
              Most things you can do here <b>requires that you authenticate</b>{' '}
              and once you've done that someone needs to give you user account
              permissions so you can actually do things.
            </p>
          </div>
        </article>
      </div>
    </div>

    <div className="tile is-ancestor">
      <div className="tile is-parent">
        <article className="tile is-child box">
          <p className="title">Authentication</p>
          <p className="has-text-centered">
            <button onClick={signIn} className="button is-info is-large">
              Sign In
            </button>
          </p>
        </article>
      </div>
      <div className="tile is-parent is-8">
        <article className="tile is-child box">
          <p className="title">Where do you want to go?</p>
          <p>
            <Link to="/help" className="is-size-5">
              Help
            </Link>
          </p>
          <p>
            <a
              href="https://tecken.readthedocs.io"
              className="is-size-5"
              rel="noopener noreferrer"
            >
              Documentation on Readthedocs
            </a>
          </p>
          <p>
            <a
              href="https://bugzilla.mozilla.org/enter_bug.cgi?product=Socorro&component=Symbols"
              className="is-size-5"
              rel="noopener noreferrer"
            >
              File a bug
            </a>
          </p>
          <p>
            <a
              href="https://github.com/mozilla-services/tecken"
              className="is-size-5"
              rel="noopener noreferrer"
            >
              Open Source code on GitHub
            </a>
          </p>
        </article>
      </div>
    </div>
  </div>
