import React from 'react'
import { Link } from 'react-router-dom'
import { observer } from 'mobx-react'

import './Home.css'
import { formatFileSize, Loading, thousandFormat } from './Common'
import Fetch from './Fetch'
import store from './Store'

const Home = observer(
  class Home extends React.Component {
    componentDidMount() {
      document.title = 'Mozilla Symbol Server'
    }

    render() {
      if (store.currentUser) {
        return <SignedInTiles user={store.currentUser} />
      }
      return (
        <AnonymousTiles
          signIn={this.props.signIn}
          authLoaded={store.signInUrl}
        />
      )
    }
  }
)

export default Home

class SignedInTiles extends React.PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      loading: true,
      loadingSettings: false,
      loadingVersions: false,
      stats: null,
      settings: null,
      versions: null
    }
  }

  componentDidMount() {
    this._fetchStats()
    if (store.currentUser.is_superuser) {
      this._fetchCurrentSettings().then(() => {
        this._fetchVersions()
      })
    }
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

  _fetchCurrentSettings = () => {
    this.setState({ loadingSettings: true })
    return Fetch('/api/_settings/', { credentials: 'same-origin' }).then(r => {
      this.setState({ loadingSettings: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            settings: response.settings
          })
        })
      } else {
        store.fetchError = r
        // Always return a promise
        return Promise.resolve()
      }
    })
  }

  _fetchVersions = () => {
    this.setState({ loadingVersions: true })
    Fetch('/api/_versions/', { credentials: 'same-origin' }).then(r => {
      this.setState({ loadingVersions: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            versions: response.versions
          })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  formatSettingValue = value => {
    if (typeof value === 'string') {
      return value
    }
    return JSON.stringify(value)
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
            {store.hasPermission('upload.upload_symbols') ? (
              <AboutUploadsTile loading={loading} stats={stats} />
            ) : (
              <AboutUploadsPermissionTile />
            )}
          </div>
          <div className="tile is-parent">
            {store.hasPermission('tokens.manage_tokens') ? (
              <AboutTokensTile loading={loading} stats={stats} />
            ) : (
              <AboutTokensPermissionTile />
            )}
          </div>
          {user.is_superuser && (
            <div className="tile is-parent">
              <article className="tile is-child box">
                <p className="title">Users</p>
                {loading || !stats ? (
                  <Loading />
                ) : (
                  <p>
                    There <b>{stats.users.total} users</b> in total of which{' '}
                    <b>{stats.users.superusers}</b>{' '}
                    {stats.users.superusers === 1
                      ? 'is superuser'
                      : 'are superusers'},
                    <b>{stats.users.not_active}</b> are inactive.
                  </p>
                )}
                <p>
                  <Link to="/users">
                    Go to <b>User Management</b>
                  </Link>
                </p>
              </article>
            </div>
          )}
        </div>

        <div className="tile is-ancestor">
          <div className="tile is-parent">
            <article className="tile is-child box">
              <p className="title">Authenticated</p>
              <p>
                You are signed in as <b>{user.email}</b>.
                <br />
                {user.is_superuser && (
                  <span>
                    You are a <b>superuser</b>.
                  </span>
                )}
              </p>
              <p style={{ marginTop: 20 }}>
                You have the following permissions:
              </p>
              {user.permissions && user.permissions.length ? (
                <ListYourPermissions permissions={user.permissions} />
              ) : (
                <AboutPermissions />
              )}
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

        {(this.state.loadingSettings || this.state.settings) && (
            <div className="tile is-ancestor">
              <div className="tile is-parent">
                <article className="tile is-child box">
                  <h3 className="title">Current Settings</h3>
                  <p>
                    Insight into the environment <b>only for superusers</b>.
                  </p>
                  {this.state.loadingSettings && <Loading />}
                  {this.state.settings && (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Setting</th>
                          <th>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {this.state.settings.map(setting => {
                          return (
                            <tr key={setting.key}>
                              <th>{setting.key}</th>
                              <td>{this.formatSettingValue(setting.value)}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                  <p className="help">
                    Note that these are only a handful of settings. They are the
                    ones that are most likely to change from one environment to
                    another. For other settings,{' '}
                    <a
                      href="https://github.com/mozilla-services/tecken/blob/master/tecken/settings.py"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      see the source code
                    </a>.
                  </p>

                  {this.state.loadingVersions ? (
                    <Loading />
                  ) : (
                    <h3 className="title" style={{marginTop: 30}}>Current Versions</h3>
                  )}
                  {this.state.versions && (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Key</th>
                          <th>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <th>React</th>
                          <td>{React.version}</td>
                        </tr>
                        {this.state.versions.map(version => {
                          return (
                            <tr key={version.key}>
                              <th>{version.key}</th>
                              <td>{this.formatSettingValue(version.value)}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                </article>
              </div>
            </div>
          )}
      </div>
    )
  }
}

const ListYourPermissions = ({ permissions }) => (
  <ul>
    {permissions.map(perm => (
      <li key={perm.id}>
        <b>{perm.name}</b>
      </li>
    ))}
  </ul>
)

const AboutPermissions = () => (
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
)

const AboutUploadsPermissionTile = () => (
  <article className="tile is-child box">
    <p className="title">Uploaded Symbols</p>
    <p>
      <i>You currently don't have permission to upload symbols.</i>
    </p>
  </article>
)

const AboutUploadsTile = ({ loading, stats }) => (
  <article className="tile is-child box">
    <p className="title">
      {loading || (stats && stats.uploads.all_uploads)
        ? 'Uploaded Symbols'
        : 'Your Uploaded Symbols'}
    </p>
    {loading || !stats ? (
      <Loading />
    ) : (
      <table className="table">
        <thead>
          <tr>
            <th />
            <th>Uploads</th>
            <th>Files</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Today</th>
            <UploadsCell
              count={stats.uploads.today.count}
              bytes={stats.uploads.today.total_size}
            />
            <UploadsCell
              count={stats.files.today.count}
              bytes={stats.files.today.total_size}
            />
          </tr>
          <tr>
            <th>Yesterday</th>
            <UploadsCell
              count={stats.uploads.yesterday.count}
              bytes={stats.uploads.yesterday.total_size}
            />
            <UploadsCell
              count={stats.files.yesterday.count}
              bytes={stats.files.yesterday.total_size}
            />
          </tr>
          <tr>
            <th>This Month</th>
            <UploadsCell
              count={stats.uploads.this_month.count}
              bytes={stats.uploads.this_month.total_size}
            />
            <UploadsCell
              count={stats.files.this_month.count}
              bytes={stats.files.this_month.total_size}
            />
          </tr>
          <tr>
            <th>This Year</th>
            <UploadsCell
              count={stats.uploads.this_year.count}
              bytes={stats.uploads.this_year.total_size}
            />
            <UploadsCell
              count={stats.files.this_year.count}
              bytes={stats.files.this_year.total_size}
            />
          </tr>
        </tbody>
      </table>
    )}
    <Link to="/uploads">
      Go to <b>Uploads</b>
    </Link>
  </article>
)

const UploadsCell = ({ count, bytes }) => {
  return <td title={formatFileSize(bytes)}>{thousandFormat(count)}</td>
}

const AboutTokensPermissionTile = () => (
  <article className="tile is-child box">
    <p className="title">API Tokens</p>
    <p>
      <i>You currently don't have permission to create API Tokens.</i>
    </p>
  </article>
)

const AboutTokensTile = ({ loading, stats }) => (
  <article className="tile is-child box">
    <p className="title">API Tokens</p>
    {loading || !stats ? (
      <Loading />
    ) : (
      <p>
        You have <b>{stats.tokens.total} API Tokens</b> of which{' '}
        <b>{stats.tokens.expired}</b> have expired.
      </p>
    )}
    <p>
      <Link to="/tokens">
        Go to <b>API Tokens</b>
      </Link>
    </p>
  </article>
)

const AnonymousTiles = ({ signIn, authLoaded }) => (
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
          {!authLoaded ? (
            <Loading />
          ) : (
            <p className="has-text-centered">
              <button onClick={signIn} className="button is-info is-large">
                Sign In
              </button>
            </p>
          )}
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
)
