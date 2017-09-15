import React, { PureComponent } from 'react'
import { Link } from 'react-router-dom'

import { format } from 'date-fns/esm'

import queryString from 'query-string'
import {
  Loading,
  DisplayDate,
  DisplayDateDifference,
  formatFileSize,
  Pagination,
  TableSubTitle,
  thousandFormat
} from './Common'
import Fetch from './Fetch'
import './Uploads.css'

import store from './Store'

class Uploads extends PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      pageTitle: 'Uploads',
      loading: true, // undone by componentDidMount
      uploads: null,
      total: null,
      batchSize: null,
      apiUrl: null,
      filter: {},
      validationErrors: null
    }
  }

  componentWillMount() {
    store.resetApiRequests()
  }

  componentDidMount() {
    document.title = this.state.pageTitle
    if (this.props.location.search) {
      this.setState(
        { filter: queryString.parse(this.props.location.search) },
        () => {
          this._fetchUploads()
        }
      )
    } else {
      this._fetchUploads()
    }

    // If the current user can only see her uploads, change the
    // title accordingly.
    if (!store.hasPermission('upload.view_all_uploads')) {
      this.setState({ pageTitle: 'Your Uploads' }, () => {
        document.title = this.state.pageTitle
      })
    }
  }

  _fetchUploads = () => {
    // delay the loading animation in case it loads really fast
    this.setLoadingTimer = window.setTimeout(() => {
      this.setState({ loading: true })
    }, 500)
    let url = '/api/uploads/'
    let qs = ''
    if (Object.keys(this.state.filter).length) {
      qs = '?' + queryString.stringify(this.state.filter)
    }
    if (qs) {
      url += qs
    }
    this.props.history.push({ search: qs })

    Fetch(url, { credentials: 'same-origin' }).then(r => {
      if (this.setLoadingTimer) {
        window.clearTimeout(this.setLoadingTimer)
      }
      if (r.status === 403 && !store.currentUser) {
        store.setRedirectTo(
          '/',
          `You have to be signed in to view "${this.pageTitle}"`
        )
        return
      }
      this.setState({ loading: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            uploads: response.uploads,
            aggregates: response.aggregates,
            total: response.total,
            batchSize: response.batch_size,
            validationErrors: null
          })
        })
      } else if (r.status === 400) {
        r.json().then(data => {
          this.setState({ loading: false, validationErrors: data.errors })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  filterOnAll = event => {
    event.preventDefault()
    const filter = this.state.filter
    delete filter.user
    this.setState({ filter: filter }, this._fetchUploads)
  }

  filterOnYours = event => {
    event.preventDefault()
    const filter = this.state.filter
    filter.user = store.currentUser.email
    this.setState({ filter: filter }, this._fetchUploads)
  }

  updateFilter = newFilters => {
    this.setState(
      {
        filter: Object.assign({}, this.state.filter, newFilters)
      },
      this._fetchUploads
    )
  }

  resetAndReload = event => {
    event.preventDefault()
    this.setState({ filter: {}, validationErrors: null }, () => {
      this._fetchUploads()
    })
  }

  render() {
    return (
      <div>
        {store.hasPermission('upload.view_all_uploads') ? (
          <div className="tabs is-centered">
            <ul>
              <li className={!this.state.filter.user && 'is-active'}>
                <Link to="/uploads" onClick={this.filterOnAll}>
                  All Uploads
                </Link>
              </li>
              <li className={this.state.filter.user && 'is-active'}>
                <Link
                  to={`/uploads?user=${store.currentUser.email}`}
                  onClick={this.filterOnYours}
                >
                  Your Uploads
                </Link>
              </li>
              <li className={false && 'is-active'}>
                <Link to="/uploads/files">All Files</Link>
              </li>
              <li className={false && 'is-active'}>
                <Link to="/uploads/upload">Upload Now</Link>
              </li>
            </ul>
          </div>
        ) : (
          <div className="tabs is-centered">
            <ul>
              <li className={!this.state.filter.user && 'is-active'}>
                <Link to="/uploads">All Uploads</Link>
              </li>
              <li className={false && 'is-active'}>
                <Link to="/uploads/upload">Upload Now</Link>
              </li>
            </ul>
          </div>
        )}
        <h1 className="title">{this.state.pageTitle}</h1>

        {this.state.loading ? (
          <Loading />
        ) : (
          <TableSubTitle
            total={this.state.total}
            page={this.state.filter.page}
            batchSize={this.state.batchSize}
          />
        )}

        {this.state.validationErrors && (
          <ShowValidationErrors
            errors={this.state.validationErrors}
            resetAndReload={this.resetAndReload}
          />
        )}

        {this.state.uploads && (
          <DisplayUploads
            uploads={this.state.uploads}
            aggregates={this.state.aggregates}
            total={this.state.total}
            batchSize={this.state.batchSize}
            location={this.props.location}
            filter={this.state.filter}
            updateFilter={this.updateFilter}
            resetAndReload={this.resetAndReload}
          />
        )}
      </div>
    )
  }
}

export default Uploads

const ShowValidationErrors = ({ errors, resetAndReload }) => {
  return (
    <div className="notification is-danger">
      <button className="delete" onClick={resetAndReload} />
      <h4>Filter validation errors</h4>
      <ul>
        {Object.keys(errors).map(key => {
          return (
            <li key={key}>
              <b>{key}</b> - <code>{errors[key]}</code>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

class DisplayUploads extends PureComponent {
  componentDidMount() {
    // XXX perhaps this stuff should happen in a componentWillReceiveProps too
    const filter = this.props.filter
    this.refs.user.value = filter.user || ''
    this.refs.size.value = filter.size || ''
    this.refs.created_at.value = filter.created_at || ''
    this.refs.completed_at.value = filter.completed_at || ''
  }

  submitForm = event => {
    event.preventDefault()
    const user = this.refs.user.value.trim()
    const size = this.refs.size.value.trim()
    const created_at = this.refs.created_at.value.trim()
    const completed_at = this.refs.completed_at.value.trim()
    this.props.updateFilter({
      page: 1,
      user,
      size,
      created_at,
      completed_at
    })
  }

  resetFilter = event => {
    this.props.resetAndReload(event)
  }

  render() {
    const { uploads, aggregates } = this.props

    const todayStr = format(new Date(), 'YYYY-MM-DD')
    const todayFullStr = format(new Date(), 'YYYY-MM-DDTHH:MM.SSSZ')
    return (
      <form onSubmit={this.submitForm}>
        <table className="table">
          <thead>
            <tr>
              <th>Files</th>
              <th>User</th>
              <th>Size</th>
              <th>Uploaded</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tfoot>
            <tr>
              <td>
                <button type="submit" className="button is-primary">
                  Filter Uploads
                </button>{' '}
                <button
                  type="button"
                  onClick={this.resetFilter}
                  className="button"
                >
                  Reset Filter
                </button>
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="user"
                  placeholder="filter..."
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="size"
                  placeholder="filter..."
                  style={{ width: 200 }}
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="created_at"
                  placeholder="filter..."
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="completed_at"
                  placeholder="filter..."
                />
              </td>
            </tr>
          </tfoot>
          <tbody>
            {uploads.map(upload => (
              <tr key={upload.id}>
                <td>
                  <Link
                    to={`/uploads/upload/${upload.id}`}
                    title="Click to see detailed information about all uploads"
                  >
                    {DisplayFilesSummary(
                      upload.files_count,
                      upload.skipped_keys.length,
                      upload.ignored_keys.length
                    )}
                  </Link>
                </td>
                <td>{upload.user.email}</td>
                <td>{formatFileSize(upload.size)}</td>
                <td>
                  <DisplayDate date={upload.created_at} />
                </td>
                <td>
                  {upload.completed_at ? (
                    <DisplayDateDifference
                      from={upload.created_at}
                      to={upload.completed_at}
                      suffix="after"
                    />
                  ) : (
                    <i>Incomplete!</i>
                  )}{' '}
                  {!upload.completed_at &&
                    !upload.cancelled_at &&
                    ` (${upload.attempts} attempts)`}
                  {!upload.completed_at &&
                    upload.cancelled_at &&
                    ` (manually cancelled)`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <Pagination
          location={this.props.location}
          total={this.props.total}
          batchSize={this.props.batchSize}
          updateFilter={this.props.updateFilter}
          currentPage={this.props.filter.page}
        />

        <ShowAggregates aggregates={aggregates} />

        <article className="message" style={{ marginTop: 50 }}>
          <div className="message-body">
            <h4 className="title is-4">Examples of Filtering</h4>
            <ul>
              <li>
                <b>User:</b> <code>@mozilla.com</code> to filter on any upload
                whose email contains this domain.
              </li>
              <li>
                <b>User:</b> <code>!peterbe@example.com</code> to filter on any
                upload whose email does NOT match that email.
              </li>
              <li>
                <b>Size:</b> <code>&gt;1mb</code> to filter all uploads{' '}
                <i>bigger</i> than one megabyte.
              </li>
              <li>
                <b>Uploaded:</b> <code>{todayStr}</code> to filter all uploads
                uploaded any time during this day (in UTC).
              </li>
              <li>
                <b>Uploaded:</b> <code>&gt;={todayFullStr}</code> to filter all
                uploads uploaded after this ISO date (in UTC).
              </li>
              <li>
                <b>Uploaded:</b> <code>today</code> (or <code>yesterday</code>)
                to filter all uploads uploaded after yesterday's UTC daybreak.
              </li>
              <li>
                <b>Completed:</b> <code>incomplete</code> to filter all uploads
                not yet completed.
              </li>
            </ul>
          </div>
        </article>
      </form>
    )
  }
}

const DisplayFilesSummary = (files, skipped, ignored) =>
  `${files} files uploaded. ${skipped} skipped. ${ignored} ignored.`

const ShowAggregates = ({ aggregates }) => {
  return (
    <nav className="level" style={{ marginTop: 60 }}>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Uploads</p>
          <p className="title">
            {aggregates.uploads.count
              ? thousandFormat(aggregates.uploads.count)
              : 'n/a'}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Upload Sizes Sum</p>
          <p className="title">
            {aggregates.uploads.size.sum
              ? formatFileSize(aggregates.uploads.size.sum)
              : 'n/a'}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Upload Sizes Avg</p>
          <p className="title">
            {aggregates.uploads.size.average
              ? formatFileSize(aggregates.uploads.size.average)
              : 'n/a'}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p
            className="heading"
            title="Files with the uploads we know we can skip"
          >
            Sum Skipped Files
          </p>
          <p className="title">
            {aggregates.uploads.skipped.sum
              ? thousandFormat(aggregates.uploads.skipped.sum)
              : 'n/a'}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading" title="Files we definitely upload to S3">
            Sum Uploaded Files
          </p>
          <p className="title">
            {aggregates.files.count
              ? thousandFormat(aggregates.files.count)
              : 'n/a'}
          </p>
        </div>
      </div>
    </nav>
  )
}
