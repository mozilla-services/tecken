import React, { Component } from 'react'
import { Link } from 'react-router-dom'

import { toDate, differenceInMinutes } from 'date-fns/esm'

import {
  Loading,
  DisplayDate,
  formatFileSize,
  DisplayDateDifference,
  BooleanIcon
} from './Common'
import './Upload.css'
import Fetch from './Fetch'
import store from './Store'

export default class Upload extends PureComponent {
  constructor(props) {
    super(props)
    this.pageTitle = 'Symbol Upload'
    this.state = {
      loading: true,
      upload: null,
      refreshingInterval: null
    }
  }
  componentWillMount() {
    store.resetApiRequests()
  }

  componentWillUnmount() {
    this.dismounted = true
  }

  componentDidMount() {
    document.title = this.pageTitle
    this.setState({ loading: true })
    this._fetchUpload(this.props.match.params.id)
  }

  goBack = event => {
    this.props.history.goBack()
  }

  _fetchUpload = id => {
    return Fetch(`/api/uploads/upload/${id}`, {
      credentials: 'same-origin'
    }).then(r => {
      if (this.dismounted) {
        return
      }
      this.setState({ loading: false })
      if (r.status === 403 && !store.currentUser) {
        store.setRedirectTo(
          '/',
          `You have to be signed in to view "${this.pageTitle}"`
        )
        return
      }
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState(
            {
              upload: response.upload,
              loading: false
            },
            () => {
              if (this.recentAndIncompleteUpload()) {
                this.keepRefreshing()
              } else if (this.state.refreshingInterval) {
                this.setState({ refreshingInterval: null })
              }
            }
          )
        })
      } else {
        store.fetchError = r
      }
    })
  }

  keepRefreshing = () => {
    let refreshingInterval = this.state.refreshingInterval
    if (!refreshingInterval) {
      refreshingInterval = 2 // start with every 2 seconds
    } else {
      refreshingInterval *= 1.5
    }
    if (!this.dismounted) {
      window.setTimeout(() => {
        if (this.dismounted) {
          return
        }
        if (this.state.upload) {
          this._fetchUpload(this.state.upload.id)
        }
      }, refreshingInterval * 1000)
      this.setState({
        refreshingInterval: refreshingInterval
      })
    }
  }

  refreshUpload = event => {
    event.preventDefault()
    this.setState({
      loading: true,
      refreshingInterval: 2 // reset this if it was manually clicked
    })
    this._fetchUpload(this.state.upload.id)
  }

  recentAndIncompleteUpload = () => {
    if (!this.state.upload.completed_at) {
      const dateObj = toDate(this.state.upload.created_at)
      return differenceInMinutes(new Date(), dateObj) < 30
    }
    return false
  }

  cancelUpload = upload => {
    return Fetch(`/api/uploads/upload/${upload.id}/cancel`, {
      method: 'POST',
      credentials: 'same-origin'
    }).then(r => {
      if (this.dismounted) {
        return
      }
      this.setState({ loading: false })
      if (r.status === 200) {
        store.setRedirectTo(`/uploads/upload/${upload.id}`, {
          message: 'Upload cancelled.',
          success: true
        })
      } else {
        store.setRedirectTo(`/uploads/upload/${upload.id}`, {
          message: 'Unable to cancel upload.',
          success: false,
          warning: true
        })
      }
    })
  }

  render() {
    return (
      <div>
        <h1 className="title">
          {this.pageTitle}
        </h1>
        <div className="is-clearfix">
          <p className="is-pulled-right">
            {this.props.history.action === 'PUSH' &&
              <a className="button is-small is-info" onClick={this.goBack}>
                <span className="icon">
                  <i className="fa fa-backward" />
                </span>{' '}
                <span>Back to Uploads</span>
              </a>}
            {this.props.history.action === 'POP' &&
              <Link to="/uploads" className="button is-small is-info">
                <span className="icon">
                  <i className="fa fa-backward" />
                </span>{' '}
                <span>Back to Uploads</span>
              </Link>}
          </p>
        </div>

        {this.state.loading && <Loading />}
        {this.state.upload &&
          !this.state.loading &&
          this.recentAndIncompleteUpload() &&
          <p className="is-pulled-right">
            <a
              className="button is-small is-primary"
              onClick={this.refreshUpload}
            >
              <span className="icon">
                <i className="fa fa-refresh" />
              </span>{' '}
              <span>Refresh</span>
            </a>
          </p>}
        {this.state.upload &&
          this.state.refreshingInterval &&
          <DisplayRefreshingInterval
            interval={this.state.refreshingInterval}
          />}
        {this.state.upload &&
          <DisplayUpload
            upload={this.state.upload}
            onCancel={this.cancelUpload}
          />}
      </div>
    )
  }
}

class DisplayRefreshingInterval extends PureComponent {
  constructor(props) {
    super(props)
    this.state = { seconds: this._roundInterval(props.interval) }
  }
  _roundInterval = interval => Math.round(Number(interval))
  componentWillUnmount() {
    this.dismounted = true
  }
  componentWillReceiveProps(nextProps) {
    this.setState({ seconds: this._roundInterval(nextProps.interval) })
  }
  componentDidMount() {
    this.loop = window.setInterval(() => {
      if (this.dismounted) {
        window.clearInterval(this.loop)
      } else {
        this.setState(state => {
          return { seconds: state.seconds - 1 }
        })
      }
    }, 1000)
  }
  render() {
    if (this.state.seconds <= 0) {
      return (
        <div className="tags">
          <span className="tag">Refreshing now</span>
        </div>
      )
    }
    let prettyTime = `${this.state.seconds} s`
    if (this.state.seconds >= 60) {
      const minutes = Math.floor(this.state.seconds / 60)
      prettyTime = `${minutes} m`
    }
    return (
      <div className="tags has-addons">
        <span className="tag">Refreshing in</span>
        <span className="tag is-primary">
          {prettyTime}
        </span>
      </div>
    )
  }
}

/* Return a new array where every item is an object.
   The reason we do this is because an upload consists of a pure array
   of skipped keys, a pure array of ignored keys and an array of
   file upload objects.
   Here we're trying to put them together in alphabetical sort order.
*/
const mergeAndSort = (uploads, skipped, ignored) => {
  const all = []
  skipped.forEach(key => {
    all.push({ key: key, skipped: true })
  })
  ignored.forEach(key => {
    all.push({ key: key, ignored: true })
  })
  uploads.forEach(upload => {
    all.push(upload)
  })
  all.sort((a, b) => {
    if (a.key < b.key) return -1
    if (a.key > b.key) return 1
    return 0
  })
  return all
}

const makeFileSummary = upload => {
  const uploaded = []
  upload.file_uploads.forEach(f => {
    uploaded.push(f.size)
  })
  return {
    uploaded: {
      count: uploaded.length,
      size: uploaded.length ? uploaded.reduce((sum, x) => sum + x) : 0
    }
  }
}

const DisplayUpload = ({ upload, onCancel }) => {
  const filesSummary = makeFileSummary(upload)

  return (
    <div>
      {upload.cancelled_at &&
        <div className="notification is-warning">
          This upload was <b>cancelled</b> from reattempts{' '}
          <DisplayDate date={upload.cancelled_at} />.
        </div>}
      <h4 className="title is-4">Metadata</h4>
      <table className="table">
        <tbody>
          <tr>
            <th>User</th>
            <td>
              {upload.user.email}
            </td>
          </tr>
          <tr>
            <th>Size</th>
            <td>
              {formatFileSize(upload.size)}
            </td>
          </tr>
          <tr>
            <th>Filename</th>
            <td>
              {upload.filename}
            </td>
          </tr>
          <tr>
            <th>Download URL</th>
            <td>
              {upload.download_url ? upload.download_url : <i>null</i>}
            </td>
          </tr>
          <tr>
            <th>Bucket Name</th>
            <td>
              {upload.bucket_name}
            </td>
          </tr>
          <tr>
            <th>Bucket Region</th>
            <td>
              {upload.bucket_region ? upload.bucket_region : <i>null</i>}
            </td>
          </tr>
          <tr>
            <th>Bucket Endpoint URL</th>
            <td>
              {upload.bucket_endpoint_url
                ? upload.bucket_endpoint_url
                : <i>null</i>}
            </td>
          </tr>
          {!upload.completed_at
            ? <tr>
                <th>Inbox Key</th>
                <td>
                  {upload.inbox_key}
                </td>
              </tr>
            : null}
          <tr>
            <th>Uploaded</th>
            <td>
              <DisplayDate date={upload.created_at} />
            </td>
          </tr>
          <tr>
            <th title="Time when its content was fully processed and uploaded, skipped or ignored">
              Completed
            </th>
            <td>
              {upload.completed_at
                ? <DisplayDate date={upload.completed_at} />
                : <i>Incomplete!</i>}
              {upload.completed_at
                ? <small>
                    {' '}(took{' '}
                    <DisplayDateDifference
                      from={upload.created_at}
                      to={upload.completed_at}
                    />)
                  </small>
                : null}
            </td>
          </tr>
          <tr>
            <th>Attempts</th>
            <td>
              {upload.attempts}
            </td>
          </tr>
        </tbody>
      </table>
      <h4 className="title is-4">Files</h4>
      <table className="table files-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Size</th>
            <th>Bucket Name</th>
            <th
              className="bool-row"
              title="True if the file overwrote an existing one with the same name"
            >
              Update
            </th>
            <th
              className="bool-row"
              title="True if the file was first gzipped before uploading"
            >
              Compressed
            </th>
            <th>Completed</th>
          </tr>
        </thead>
        <tbody>
          {mergeAndSort(
            upload.file_uploads,
            upload.skipped_keys,
            upload.ignored_keys
          ).map(file => {
            if (file.skipped || file.ignored) {
              return (
                <tr key={file.key}>
                  <td>
                    {file.key}
                  </td>
                  <td colSpan={6}>
                    <b>{file.skipped ? 'Skipped' : 'Ignored'}</b>{' '}
                    {file.skipped
                      ? <small>
                          Not uploaded because existing file has the same size
                        </small>
                      : <small>
                          File OK in the archive but deliberately not uploaded
                        </small>}
                  </td>
                </tr>
              )
            }
            return (
              <tr key={file.key}>
                <td>
                  {file.key}
                </td>
                <td>
                  {formatFileSize(file.size)}
                </td>
                <td>
                  {file.bucket_name}
                </td>
                <td>
                  {BooleanIcon(file.update)}
                </td>
                <td>
                  {BooleanIcon(file.compressed)}
                </td>
                <td>
                  {file.completed_at
                    ? <DisplayDate date={file.completed_at} />
                    : <i>Incomplete!</i>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <h4 className="title is-4">Files Summary</h4>
      <dl>
        <dt>Files Uploaded</dt>
        <dd>
          {filesSummary.uploaded.count}{' '}
          {` (${formatFileSize(filesSummary.uploaded.size)})`}
        </dd>

        <dt>Files Not Uploaded</dt>
        <dd>
          {upload.skipped_keys.length}
        </dd>
      </dl>

      {!upload.completed_at &&
        upload.cancellable &&
        <div style={{ marginTop: 100 }}>
          <CancelReattemptForm upload={upload} onCancel={onCancel} />
        </div>}
    </div>
  )
}

class CancelReattemptForm extends PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      askedConfirm: false
    }
  }
  toggleConfirm = event => {
    event.preventDefault()
    this.setState({ askedConfirm: !this.state.askedConfirm })
  }
  confirmCancel = event => {
    event.preventDefault()
    this.props.onCancel(this.props.upload)
  }
  render() {
    if (this.state.askedConfirm) {
      return (
        <article className="message is-danger">
          <div className="message-header">
            <p>Stop Reattempts?</p>
          </div>
          <div className="message-body">
            <p>Please confirm.</p>
            <button
              type="button"
              className="button is-danger"
              onClick={this.confirmCancel}
            >
              Do it
            </button>{' '}
            <button
              type="button"
              className="button"
              onClick={this.toggleConfirm}
            >
              Cancel
            </button>
          </div>
        </article>
      )
    }
    return (
      <article className="message is-warning">
        <div className="message-header">
          <p>Stop Reattempts?</p>
        </div>
        <div className="message-body">
          <p>
            This upload is <b>incomplete</b> and <b>can be cancelled</b> for
            further reattempts.
          </p>
          <button
            type="button"
            className="button is-warning"
            onClick={this.toggleConfirm}
          >
            Stop
          </button>
        </div>
      </article>
    )
  }
}
