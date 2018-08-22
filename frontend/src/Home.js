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

const formatSettingValue = (value, key = null) => {
  if (typeof value === 'string') {
    return value
  }
  // exceptions for fancyness
  if (key === 'Tecken' && value) {
    return TeckenVersionFancy(value)
  }
  return JSON.stringify(value)
}

const TeckenVersionFancy = versions => {
  const keys = Object.keys(versions)
  keys.sort()
  return (
    <dl>
      {keys.map(key => {
        let value = versions[key]
        if (key === 'build' || key === 'source') {
          value = (
            <a href={value} target="_blank" rel="noopener noreferrer">
              {value}
            </a>
          )
        } else if (key === 'commit') {
          const commitUrl = `https://github.com/mozilla-services/tecken/commit/${value}`
          const treeUrl = `https://github.com/mozilla-services/tecken/tree/${value}`
          const sha = value.substring(0, 7)
          value = [
            <a key="commit" href={commitUrl}>
              commit @ {sha}
            </a>,
            <br key="break" />,
            <a key="tree" href={treeUrl}>
              tree @ {sha}
            </a>
          ]
        } else if (key === 'version') {
          const releaseUrl = `https://github.com/mozilla-services/tecken/releases/tag/${value}`
          value = <a href={releaseUrl}>{value}</a>
        }
        return [<dt key="key">{key}</dt>, <dd key="value">{value}</dd>]
      })}
    </dl>
  )
}

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
    Fetch('/api/stats/', { credentials: 'same-origin' }).then(r => {
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

  render() {
    const { user } = this.props
    const { stats, loading } = this.state
    return (
      <div>
        <div className="tile is-ancestor">
          <div
            className={user.is_superuser ? 'tile is-parent' : 'tile is-parent'}
          >
            {store.hasPermission('upload.upload_symbols') ? (
              <UploadsStatsTile loading={loading} stats={stats} />
            ) : (
              <AboutUploadsPermissionTile />
            )}
          </div>
          <div className="tile is-parent">
            <DownloadsStatsTile loading={loading} stats={stats} />
          </div>
        </div>

        <div className="tile is-ancestor">
          <div className="tile is-parent">
            <YouTile user={user} />
          </div>

          {user.is_superuser && (
            <div className="tile is-parent">
              <UsersTile loading={loading} stats={stats} />
            </div>
          )}

          <div
            className={
              user.is_superuser ? 'tile is-parent is-4' : 'tile is-parent is-8'
            }
          >
            <LinksTile />
          </div>
        </div>

        {(this.state.loadingSettings || this.state.settings) && (
          <div className="tile is-ancestor">
            <div className="tile is-parent">
              <EnvironmentTile
                loadingSettings={this.state.loadingSettings}
                settings={this.state.settings}
                loadingVersions={this.state.loadingVersions}
                versions={this.state.versions}
              />
            </div>
          </div>
        )}
      </div>
    )
  }
}

const EnvironmentTile = ({
  loadingSettings,
  settings,
  loadingVersions,
  versions
}) => (
  <article className="tile is-child box">
    <h3 className="title">Current Settings</h3>
    <p>
      Insight into the environment <b>only for superusers</b>.
    </p>
    {loadingSettings && <Loading />}
    {settings && (
      <table className="table is-fullwidth">
        <thead>
          <tr>
            <th>Setting</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {settings.map(setting => {
            return (
              <tr key={setting.key}>
                <th>{setting.key}</th>
                <td>{formatSettingValue(setting.value)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )}
    <p className="help">
      Note that these are only a handful of settings. They are the ones that are
      most likely to change from one environment to another. For other settings,{' '}
      <a
        href="https://github.com/mozilla-services/tecken/blob/master/tecken/settings.py"
        target="_blank"
        rel="noopener noreferrer"
      >
        see the source code
      </a>
      .
    </p>

    {loadingVersions ? (
      <Loading />
    ) : (
      <h3 className="title" style={{ marginTop: 30 }}>
        Current Versions
      </h3>
    )}
    {versions && (
      <table className="table is-fullwidth">
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
          {versions.map(version => {
            return (
              <tr key={version.key}>
                <th>{version.key}</th>
                <td>{formatSettingValue(version.value, version.key)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )}
  </article>
)

const YouTile = ({ user }) => (
  <article className="tile is-child box">
    <p className="title">Authenticated</p>
    <p>
      You are signed in as <b>{user.email}</b>.<br />
      {user.is_superuser && (
        <span>
          You are a <b>superuser</b>.
        </span>
      )}
    </p>
    <p style={{ marginTop: 20 }}>You have the following permissions:</p>
    {user.permissions && user.permissions.length ? (
      <ListYourPermissions permissions={user.permissions} />
    ) : (
      <AboutPermissions />
    )}
  </article>
)

const UsersTile = ({ loading, stats }) => (
  <article className="tile is-child box">
    <p className="title">Users</p>
    {loading || !stats ? (
      <Loading />
    ) : (
      <p>
        There <b>{stats.users.total} users</b> in total of which{' '}
        <b>{stats.users.superusers}</b>{' '}
        {stats.users.superusers === 1 ? 'is superuser' : 'are superusers'},
        <b>{stats.users.not_active}</b> are inactive.
      </p>
    )}
    <p>
      <Link to="/users">
        Go to <b>User Management</b>
      </Link>
    </p>
  </article>
)

const LinksTile = () => (
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
)

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

const UploadsStatsTile = ({ loading, stats }) => (
  <article className="tile is-child box">
    <p className="title">
      {loading || (stats && stats.uploads.all_uploads)
        ? 'Uploaded Symbols'
        : 'Your Uploaded Symbols'}
    </p>
    {loading || !stats ? (
      <Loading />
    ) : (
      <table className="table is-fullwidth">
        <thead>
          <tr>
            <th />
            <th colSpan={2}>
              <Link to="/uploads">Uploads</Link>
            </th>
            <th colSpan={2}>
              <Link
                to="/uploads/files"
                title="Files from .zip uploads we actually upload to S3"
              >
                Uploaded Files
              </Link>
            </th>
          </tr>
        </thead>
        <tbody>
          <UploadsRow
            title="Today"
            uploads={stats.uploads.today}
            files={stats.files.today}
          />
          <UploadsRow
            title="Yesterday"
            uploads={stats.uploads.yesterday}
            files={stats.files.yesterday}
          />
          <UploadsRow
            title="This Month"
            uploads={stats.uploads.this_month}
            files={stats.files.this_month}
          />
        </tbody>
      </table>
    )}
  </article>
)

const UploadsRow = ({ title, uploads, files }) => {
  return (
    <tr>
      <th>{title}</th>
      <td>{thousandFormat(uploads.count)}</td>
      <td>{formatFileSize(uploads.total_size)}</td>
      <td>{thousandFormat(files.count)}</td>
      <td>{formatFileSize(files.total_size)}</td>
    </tr>
  )
}

const DownloadsStatsTile = ({ loading, stats }) => (
  <article className="tile is-child box">
    <p className="title">Downloads</p>
    {loading || !stats ? (
      <Loading />
    ) : (
      <table className="table is-fullwidth">
        <thead>
          <tr>
            <th />
            <th>
              <Link to="/downloads/missing">Recorded Missing</Link>
            </th>
            <th>
              <Link to="/downloads/microsoft">Microsoft Downloads</Link>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Today</th>
            <TableCountCell count={stats.downloads.missing.today.count} />
            <TableCountCell count={stats.downloads.microsoft.today.count} />
          </tr>
          <tr>
            <th>Yesterday</th>
            <TableCountCell count={stats.downloads.missing.yesterday.count} />
            <TableCountCell count={stats.downloads.microsoft.yesterday.count} />
          </tr>
          <tr>
            <th>This Month</th>
            <TableCountCell count={stats.downloads.missing.this_month.count} />
            <TableCountCell
              count={stats.downloads.microsoft.this_month.count}
            />
          </tr>
        </tbody>
      </table>
    )}
  </article>
)

const TableCountCell = ({ count }) => {
  return <td>{thousandFormat(count)}</td>
}

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
        <LinksTile />
      </div>
    </div>
  </div>
)
