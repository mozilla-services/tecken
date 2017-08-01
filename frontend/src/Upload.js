import React, { Component } from 'react'

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

export default class Upload extends Component {
  constructor(props) {
    super(props)
    this.pageTitle = 'Symbol Upload'
    this.state = {
      loading: true,
      upload: null
    }
  }
  componentWillMount() {
    store.resetApiRequests()
  }

  componentDidMount() {
    document.title = this.pageTitle
    this._fetchUpload(this.props.match.params.id)
  }

  goBack = event => {
    this.props.history.goBack()
  }

  _fetchUpload = id => {
    this.setState({ loading: true })
    Fetch(`/api/uploads/upload/${id}`, { credentials: 'same-origin' }).then(r => {
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
          this.setState({
            upload: response.upload,
            loading: false
          })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  render() {
    return (
      <div>
        <h1 className="title">
          {this.pageTitle}
        </h1>
        {this.props.history.length > 1
          ? <p>
              <a className="button is-small is-info" onClick={this.goBack}>
                <span className="icon">
                  <i className="fa fa-backward" />
                </span>{' '}
                <span>Back to Uploads</span>
              </a>
            </p>
          : null}

        {this.state.loading && <Loading />}
        {this.state.upload && <DisplayUpload upload={this.state.upload} />}
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

const DisplayUpload = ({ upload }) => {
  const filesSummary = makeFileSummary(upload)

  return (
    <div>
      <h3 className="title">Metadata</h3>
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
            <td>{upload.attempts}</td>
          </tr>
        </tbody>
      </table>
      <h3 className="title">Files</h3>
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

      <h3 className="title">Files Summary</h3>
      <dl>
        <dt>Files Uploaded</dt>
        <dd>
          {filesSummary.uploaded.count}{' '}
          {` (${formatFileSize(filesSummary.uploaded.size)})`}
        </dd>

        <dt>Files Not Uploaded</dt>
        <dd>{upload.skipped_keys.length}</dd>
      </dl>
    </div>
  )
}
