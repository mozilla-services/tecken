import React, { Component } from 'react'
import { Link } from 'react-router-dom'

import queryString from 'query-string'
import {
  Loading,
  DisplayDate,
  formatFileSize,
  Pagination,
  BooleanIcon,
  TableSubTitle
} from './Common'
import Fetch from './Fetch'
import './Upload.css' // they have enough in common
import './Files.css'

import store from './Store'

class Files extends Component {
  constructor(props) {
    super(props)
    this.pageTitle = 'Files Uploaded'
    this.state = {
      loading: true, // undone by componentDidMount
      files: null,
      total: null,
      batchSize: null,
      apiUrl: null,
      filter: {}
    }
  }

  componentWillMount() {
    store.resetApiRequests()
  }

  componentDidMount() {
    document.title = this.pageTitle
    if (this.props.location.search) {
      this.setState(
        { filter: queryString.parse(this.props.location.search) },
        () => {
          this._fetchFiles(false)
        }
      )
    } else {
      this._fetchFiles(false)
    }
  }

  _fetchFiles = (updateHistory = true) => {
    // delay the loading animation in case it loads really fast
    this.setLoadingTimer = window.setTimeout(() => {
      this.setState({ loading: true })
    }, 500)
    let url = '/api/uploads/files'
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
            files: response.files,
            total: response.total,
            batchSize: response.batch_size
          })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  filterOnAll = event => {
    event.preventDefault()
    const filter = this.state.filter
    // delete filter.user
    delete filter.download
    filter.page = 1
    filter.key = ''
    filter.size = ''
    this.setState({ filter: filter }, this._fetchFiles)
  }

  filterOnMicrosoftDownloads = event => {
    event.preventDefault()
    const filter = this.state.filter
    filter.download = 'microsoft'
    filter.page = 1
    this.setState({ filter: filter }, this._fetchFiles)
  }

  updateFilter = newFilters => {
    this.setState(
      {
        filter: Object.assign({}, this.state.filter, newFilters)
      },
      this._fetchFiles
    )
  }

  render() {
    return (
      <div>
        {store.hasPermission('view_all_uploads')
          ? <div className="tabs is-centered">
              <ul>
                <li className={!this.state.filter.download && 'is-active'}>
                  <Link to="/uploads/files" onClick={this.filterOnAll}>
                    All Files
                  </Link>
                </li>
                <li
                  className={
                    this.state.filter.download === 'microsoft' && 'is-active'
                  }
                >
                  <Link
                    to="/uploads/files?download=microsoft"
                    onClick={this.filterOnMicrosoftDownloads}
                  >
                    Microsoft Download Files
                  </Link>
                </li>
                <li className={false && 'is-active'}>
                  <Link to="/uploads">All Uploads</Link>
                </li>
              </ul>
            </div>
          : null}
        <h1 className="title">
          {this.pageTitle}
        </h1>

        {this.state.loading
          ? <Loading />
          : <TableSubTitle
              total={this.state.total}
              page={this.state.filter.page}
              batchSize={this.state.batchSize}
            />}

        {this.state.files &&
          <DisplayFiles
            files={this.state.files}
            total={this.state.total}
            batchSize={this.state.batchSize}
            location={this.props.location}
            filter={this.state.filter}
            updateFilter={this.updateFilter}
          />}
      </div>
    )
  }
}

export default Files

class DisplayFiles extends Component {
  componentDidMount() {
    // XXX perhaps this stuff should happen in a componentWillReceiveProps too
    const filter = this.props.filter
    this.refs.key.value = filter.key || ''
    this.refs.size.value = filter.size || ''
    this.refs.bucketName.value = filter.bucket_name || ''
    // this.refs.created_at.value = filter.created_at || ''
    // this.refs.completed_at.value = filter.completed_at || ''
  }

  submitForm = event => {
    event.preventDefault()
    const key = this.refs.key.value.trim()
    const size = this.refs.size.value.trim()
    const bucketName = this.refs.bucketName.value.trim()
    // const created_at = this.refs.created_at.value.trim()
    // const completed_at = this.refs.completed_at.value.trim()
    this.props.updateFilter({
      key,
      size,
      bucket_name: bucketName,
      page: 1
    })
  }

  resetFilter = event => {
    this.refs.key.value = ''
    this.refs.size.value = ''
    this.refs.bucketName.value = ''
    // this.refs.created_at.value = ''
    // this.refs.completed_at.value = ''
    this.submitForm(event)
    this.props.updateFilter({ download: '' })
  }
  render() {
    const { files } = this.props

    // const todayStr = format(new Date(), 'YYYY-MM-DD')
    // const todayFullStr = format(new Date(), 'YYYY-MM-DDTHH:MM.SSSZ')
    return (
      <form onSubmit={this.submitForm}>
        <table className="table files-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Size</th>
              <th>Bucket Name</th>
              <th>Metadata</th>
            </tr>
          </thead>
          <tfoot>
            <tr>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="key"
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
                  ref="bucketName"
                  placeholder="filter..."
                />
              </td>
              <td>
                <button type="submit" className="button is-primary">
                  Filter Files
                </button>{' '}
                <button
                  type="button"
                  onClick={this.resetFilter}
                  className="button"
                >
                  Reset Filter
                </button>
              </td>
            </tr>
          </tfoot>
          <tbody>
            {files.map(file =>
              <tr key={file.id}>
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
                  <table className="table metadata-table">
                    <tbody>
                      <tr>
                        <th>Upload</th>
                        <td colSpan={6}>
                          {file.upload
                            ? <Link to={`/uploads/upload/${file.upload.id}`}>
                                <DisplayDate date={file.upload.created_at} />
                                {' by '}
                                {file.upload.user.email}
                              </Link>
                            : <i>n/a</i>}
                        </td>
                      </tr>
                      <tr>
                        <th>Date</th>
                        <td colSpan={6}>
                          <DisplayDate date={file.completed_at} />
                        </td>
                      </tr>
                      <tr>
                        <th title="Did it replace an existing file">Update</th>
                        <td>
                          {BooleanIcon(file.update)}
                        </td>
                        <th title="Was it gzip compressed before upload">
                          Compressed
                        </th>
                        <td>
                          {BooleanIcon(file.compressed)}
                        </td>
                        <th title="Was it uploaded by the Microsoft Download job">
                          Microsoft
                        </th>
                        <td>
                          {BooleanIcon(file.microsoft_download)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <Pagination
          location={this.props.location}
          total={this.props.total}
          batchSize={this.props.batchSize}
          updateFilter={this.props.updateFilter}
          currentPage={this.props.filter.page}
        />

        {/* <article className="message" style={{ marginTop: 50 }}>
          <div className="message-body">
            <h4 className="title is-4">Examples of Filtering</h4>
            <ul>
              <li>
                <b>User:</b> <code>@mozilla.com</code> to filter on any upload
                whose email contains this domain.
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
                <b>Completed:</b> <code>incomplete</code> to filter all uploads
                not yet completed.
              </li>
            </ul>
          </div>
        </article> */}
      </form>
    )
  }
}
