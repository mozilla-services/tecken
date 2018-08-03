import React from 'react'
import { Link } from 'react-router-dom'
import Fetch from './Fetch'
import store from './Store'

import {
  Loading,
  Pagination,
  TableSubTitle,
  DisplayDate,
  DisplayDateDifference,
  thousandFormat,
  formatFileSize,
  ShowValidationErrors,
  filterToQueryString,
  parseQueryString
} from './Common'

class DownloadsMicrosoft extends React.PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      pageTitle: 'Microsoft Downloads',
      loading: true,
      downloads: null,
      aggregates: null,
      total: null,
      batchSize: null,
      apiUrl: null,
      filter: {},
      validationErrors: null
    }
  }

  componentDidMount() {
    document.title = this.state.pageTitle
    store.resetApiRequests()

    if (this.props.location.search) {
      this.setState(
        { filter: parseQueryString(this.props.location.search) },
        () => {
          this._fetchMissing()
        }
      )
    } else {
      this._fetchMissing()
    }
  }

  _fetchMissing = () => {
    // delay the loading animation in case it loads really fast
    this.setLoadingTimer = window.setTimeout(() => {
      if (!this.dismounted) {
        this.setState({ loading: true })
      }
    }, 500)
    let url = '/api/downloads/microsoft/'
    const qs = filterToQueryString(this.state.filter)
    if (qs) {
      url += '?' + qs
    }
    this.props.history.push({ search: qs })

    return Fetch(url, {}).then(r => {
      if (this.setLoadingTimer) {
        window.clearTimeout(this.setLoadingTimer)
      }
      this.setState({ loading: false })
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null
        }
        return r.json().then(response => {
          this.setState({
            downloads: response.microsoft_downloads,
            aggregates: response.aggregates,
            total: response.total,
            batchSize: response.batch_size,
            validationErrors: null
          })
        })
      } else if (r.status === 400) {
        return r.json().then(data => {
          this.setState({
            loading: false,
            refreshing: false,
            validationErrors: data.errors
          })
        })
      } else {
        store.fetchError = r
        // Always return a promise
        return Promise.resolve()
      }
    })
  }

  updateFilter = newFilters => {
    this.setState(
      {
        filter: Object.assign({}, this.state.filter, newFilters)
      },
      this._fetchMissing
    )
  }

  resetAndReload = event => {
    event.preventDefault()
    this.setState({ filter: {}, validationErrors: null }, () => {
      this._fetchMissing()
    })
  }

  render() {
    return (
      <div>
        <div className="tabs is-centered">
          <ul>
            <li>
              <Link to="/downloads/missing">Downloads Missing</Link>
            </li>
            <li className="is-active">
              <Link to="/downloads/microsoft">Microsoft Downloads</Link>
            </li>
          </ul>
        </div>
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

        {this.state.downloads && (
          <DisplayDownloads
            downloads={this.state.downloads}
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

export default DownloadsMicrosoft

class DisplayDownloads extends React.PureComponent {
  componentDidMount() {
    this._updateFilterInputs(this.props.filter)
  }

  componentWillReceiveProps(nextProps) {
    this._updateFilterInputs(nextProps.filter)
  }

  _updateFilterInputs = filter => {
    this.refs.created_at.value = filter.created_at || ''
    this.refs.symbol.value = filter.symbol || ''
    this.refs.debugid.value = filter.debugid || ''
    this.refs.filename.value = filter.filename || ''
    this.stateFilter.value = filter.state || ''
    if (this.stateError) {
      this.stateError.value = filter.error || ''
    }
  }

  submitForm = event => {
    event.preventDefault()
    const created_at = this.refs.created_at.value.trim()
    const symbol = this.refs.symbol.value.trim()
    const debugid = this.refs.debugid.value.trim()
    const filename = this.refs.filename.value.trim()
    const stateFilter = this.stateFilter.value
    const stateError = this.stateError ? this.stateError.value : ''
    this.props.updateFilter({
      page: 1,
      created_at,
      symbol,
      debugid,
      filename,
      state: stateFilter,
      error: stateError
    })
  }

  resetFilter = event => {
    this.refs.symbol.value = ''
    this.refs.debugid.value = ''
    this.refs.filename.value = ''
    this.refs.created_at.value = ''
    this.stateFilter.value = ''
    if (this.stateError) {
      this.stateError.value = ''
    }
    this.props.resetAndReload(event)
  }

  render() {
    const { downloads, aggregates } = this.props

    return (
      <form onSubmit={this.submitForm}>
        <table className="table files-table is-fullwidth">
          <thead>
            <tr>
              <th>URI</th>
              <th>File Upload</th>
              <th>Error</th>
              <th>Date</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tfoot>
            <tr>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="symbol"
                  placeholder="symbol..."
                  style={{ width: '30%' }}
                />{' '}
                <input
                  type="text"
                  className="input"
                  ref="debugid"
                  placeholder="debugid..."
                  style={{ width: '30%' }}
                />{' '}
                <input
                  type="text"
                  className="input"
                  ref="filename"
                  placeholder="filename..."
                  style={{ width: '30%' }}
                />
              </td>
              <td colSpan={2}>
                <StateChoice
                  stateRef={input => (this.stateFilter = input)}
                  stateError={input => (this.stateError = input)}
                  initialState={this.props.filter.state}
                  initialError={this.props.filter.error}
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

              <td colSpan={2} style={{ width: 172 }} className="buttons">
                <button type="submit" className="button is-primary">
                  Filter
                </button>
                <button
                  type="button"
                  onClick={this.resetFilter}
                  className="button"
                >
                  Reset
                </button>
              </td>
            </tr>
          </tfoot>
          <tbody>
            {downloads.map(download => (
              <tr key={download.id}>
                <td
                  className="file-key"
                  title={`code_file=${
                    download.missing_symbol.code_file
                  }   code_id=${download.missing_symbol.code_id}`}
                >
                  {download.missing_symbol.symbol}/
                  {download.missing_symbol.debugid}/
                  {download.missing_symbol.filename}
                </td>
                <td>
                  {download.file_upload ? (
                    <ShowFileUpload file_upload={download.file_upload} />
                  ) : (
                    'n/a'
                  )}
                </td>
                <td className="is-clipped">
                  {download.error ? (
                    <span className="has-text-danger">{download.error}</span>
                  ) : (
                    '-'
                  )}
                </td>
                <td>
                  <DisplayDate date={download.created_at} />
                </td>
                <td>
                  {download.completed_at && (
                    <DisplayDateDifference
                      from={download.created_at}
                      to={download.completed_at}
                      suffix="after"
                    />
                  )}
                  {!download.completed_at && download.error && 'n/a'}
                  {!download.completed_at &&
                    !download.error && <i>Incomplete!</i>}
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
      </form>
    )
  }
}

class StateChoice extends React.PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      showErrorInput: this.props.initialState === 'specific-error'
    }
  }

  onChangeSelect = event => {
    this.setState({
      showErrorInput: event.target.value === 'specific-error'
    })
  }

  render() {
    return (
      <div className="select">
        <select ref={this.props.stateRef} onChange={this.onChangeSelect}>
          <option value="">ALL</option>
          <option value="errored">Errored</option>
          <option value="specific-error">Specific Error</option>
          <option value="file-upload">Has file upload</option>
          <option value="no-file-upload">No file upload</option>
        </select>

        {this.state.showErrorInput && (
          <input
            type="text"
            className="input"
            placeholder="Error..."
            ref={this.props.stateError}
          />
        )}
      </div>
    )
  }
}

const ShowFileUpload = ({ file_upload }) => (
  <Link to={`/uploads/files/file/${file_upload.id}`}>
    {formatFileSize(file_upload.size)}
  </Link>
)

const ShowAggregates = ({ aggregates }) => {
  return (
    <nav className="level" style={{ marginTop: 60 }}>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Total</p>
          <p className="title">
            {thousandFormat(aggregates.microsoft_downloads.total)}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Files Uploaded</p>
          <p className="title">
            {thousandFormat(aggregates.microsoft_downloads.file_uploads.count)}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Files Uploaded Sum Size</p>
          <p className="title">
            {formatFileSize(
              aggregates.microsoft_downloads.file_uploads.size.sum
            )}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Files Uploaded Avg Size</p>
          <p className="title">
            {formatFileSize(
              aggregates.microsoft_downloads.file_uploads.size.average
            )}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">File Uploads Skipped</p>
          <p className="title">
            {thousandFormat(aggregates.microsoft_downloads.skipped)}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Errored</p>
          <p className="title">
            {thousandFormat(aggregates.microsoft_downloads.errors)}
          </p>
        </div>
      </div>
    </nav>
  )
}
