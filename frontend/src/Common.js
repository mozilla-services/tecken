import React from 'react'
import FontAwesome from 'react-fontawesome'
import 'font-awesome/css/font-awesome.css'
import { Link } from 'react-router-dom'
import queryString from 'query-string'

import {
  toDate,
  isBefore,
  formatDistance,
  formatDistanceStrict,
  differenceInSeconds,
  differenceInMilliseconds
} from 'date-fns/esm'

export const Loading = () => (
  <p className="has-text-centered">
    <span className="icon is-large">
      <FontAwesome name="cog" spin size="5x" />
      <span className="sr-only">Loading...</span>
    </span>
  </p>
)

export const DisplayDate = ({ date }) => {
  if (date === null) {
    throw new Error('date is null')
  }
  const dateObj = toDate(date)
  const now = new Date()
  if (isBefore(dateObj, now)) {
    return <span title={date}>{formatDistance(date, now)} ago</span>
  } else {
    return <span title={date}>in {formatDistance(date, now)}</span>
  }
}

export const DisplayDateDifference = ({ from, to, suffix = '' }) => {
  const fromObj = toDate(from)
  const toObj = toDate(to)
  const secDiff = differenceInSeconds(toObj, fromObj)
  if (secDiff === 0) {
    const msecDiff = differenceInMilliseconds(toObj, fromObj)
    if (msecDiff > 0) {
      return (
        <span title={`From ${fromObj} to ${toObj}`}>
          {msecDiff} ms
          {suffix && ` ${suffix}`}
        </span>
      )
    }
  }
  return (
    <span title={`From ${fromObj} to ${toObj}`}>
      {formatDistanceStrict(fromObj, toObj)}
      {suffix && ` ${suffix}`}
    </span>
  )
}

export const thousandFormat = x => {
  return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

export const formatFileSize = (bytes, decimals = 0) => {
  if (!bytes) return '0 bytes'
  var k = 1024
  var dm = decimals + 1 || 3
  var sizes = ['bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
  var i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

export const formatSeconds = seconds => {
  if (seconds < 1) {
    // milliseconds
    return (seconds * 1000).toFixed(0) + 'ms'
  } else if (seconds > 3000) {
    return (seconds / 60).toFixed(1) + 'm'
  } else if (seconds < 60) {
    return seconds.toFixed(1) + 's'
  } else {
    const minutes = Math.floor(seconds / 60)
    seconds = Math.round(seconds % 60)
    return `${minutes}m${seconds}s`
  }
}
export const BooleanIcon = bool => (
  <span className="icon" style={{ color: bool ? 'green' : 'red' }}>
    <i className={bool ? 'fa fa-check' : 'fa fa-close'} />
  </span>
)

export const Pagination = ({
  location,
  total,
  batchSize,
  currentPage,
  updateFilter
}) => {
  if (!currentPage) {
    currentPage = 1
  } else if (typeof currentPage === 'string') {
    currentPage = parseInt(currentPage, 10)
  }

  const nextPageUrl = page => {
    const qs = queryString.parse(location.search)
    qs.page = page
    return location.pathname + '?' + queryString.stringify(qs)
  }

  const goTo = (event, page) => {
    event.preventDefault()
    updateFilter({ page })
  }

  const isOverflow = page => {
    // return true if doesn't make sense to go to this page
    return page < 1 || (page - 1) * batchSize >= total
  }

  return (
    <nav className="pagination is-right">
      <Link
        className="pagination-previous"
        to={nextPageUrl(currentPage - 1)}
        onClick={e => goTo(e, currentPage - 1)}
        disabled={isOverflow(currentPage - 1)}
      >
        Previous
      </Link>
      <Link
        to={nextPageUrl(currentPage + 1)}
        className="pagination-next"
        onClick={e => goTo(e, currentPage + 1)}
        disabled={isOverflow(currentPage + 1)}
      >
        Next page
      </Link>
    </nav>
  )
}

export const TableSubTitle = ({ total, page, batchSize }) => {
  if (total === null) {
    return null
  }
  page = page || 1
  const totalPages = Math.ceil(total / batchSize)
  return (
    <h2 className="subtitle">
      {thousandFormat(total)} Found (Page {thousandFormat(page)} of{' '}
      {thousandFormat(totalPages)})
    </h2>
  )
}

export const pluralize = (number, singular, plural) => {
  if (number === 1) {
    return `1 ${singular}`
  } else {
    return `${number} ${plural}`
  }
}

export const DisplayFilesSummary = (files, incomplete, skipped, ignored) => {
  const sentences = []
  sentences.push(pluralize(files, 'file uploaded', 'files uploaded'))
  if (incomplete) {
    sentences.push(pluralize(incomplete, 'file incomplete', 'files incomplete'))
  }
  sentences.push(`${skipped} skipped`)
  // Currently ignoring the 'ignored'
  return sentences.join('. ') + '.'
}

export const ShowValidationErrors = ({ errors, resetAndReload }) => {
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

export const filterToQueryString = (filterObj, overrides) => {
  let qs = ''
  let copy = {}
  Object.keys(filterObj).forEach(key => {
    if (filterObj[key]) {
      copy[key] = filterObj[key]
    }
  })
  if (overrides) {
    copy = Object.assign(copy, overrides)
  }
  if (Object.keys(copy).length) {
    qs = queryString.stringify(copy)
  }
  return qs
}

const URLTag = url => <span className="url">{url}</span>

export const ShowUploadMetadata = ({ upload }) => (
  <table className="table is-fullwidth">
    <tbody>
      <tr>
        <th>User</th>
        <td>{upload.user.email}</td>
      </tr>
      <tr>
        <th>Size</th>
        <td>{formatFileSize(upload.size)}</td>
      </tr>
      <tr>
        <th>Filename</th>
        <td>{upload.filename}</td>
      </tr>
      <tr>
        <th>Try Symbols</th>
        <td>{upload.try_symbols ? 'Yes' : 'No'}</td>
      </tr>
      <tr>
        <th>Download URL</th>
        <td>
          {upload.download_url ? URLTag(upload.download_url) : <i>null</i>}
        </td>
      </tr>
      {upload.download_url && (
        <tr>
          <th>Redirect URLs</th>
          <td>
            {!upload.redirect_urls.length && <i>n/a</i>}
            {upload.redirect_urls.length ? (
              <ol start="0" className="redirect-urls">
                <li>{URLTag(upload.download_url)}</li>
                {upload.redirect_urls.map(url => <li>{URLTag(url)}</li>)}
              </ol>
            ) : null}
          </td>
        </tr>
      )}
      <tr>
        <th>Bucket Name</th>
        <td>{upload.bucket_name}</td>
      </tr>
      <tr>
        <th>Bucket Region</th>
        <td>{upload.bucket_region ? upload.bucket_region : <i>null</i>}</td>
      </tr>
      <tr>
        <th>Bucket Endpoint URL</th>
        <td>
          {upload.bucket_endpoint_url ? (
            upload.bucket_endpoint_url
          ) : (
            <i>null</i>
          )}
        </td>
      </tr>
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
          {upload.completed_at ? (
            <DisplayDate date={upload.completed_at} />
          ) : (
            <i>Incomplete!</i>
          )}
          {upload.completed_at ? (
            <small>
              {' '}
              (took{' '}
              <DisplayDateDifference
                from={upload.created_at}
                to={upload.completed_at}
              />)
            </small>
          ) : null}
        </td>
      </tr>
    </tbody>
  </table>
)

export const ShowFileMetadata = ({ file }) => (
  <table className="table is-fullwidth">
    <tbody>
      <tr>
        <th>Key</th>
        <td>{file.key}</td>
      </tr>
      <tr>
        <th>Size</th>
        <td>{formatFileSize(file.size)}</td>
      </tr>
      <tr>
        <th>Bucket Name</th>
        <td>{file.bucket_name}</td>
      </tr>
      <tr>
        <th>Update</th>
        <td>{BooleanIcon(file.update)}</td>
      </tr>
      <tr>
        <th>Compressed</th>
        <td>{BooleanIcon(file.compressed)}</td>
      </tr>
      <tr>
        <th>Uploaded</th>
        <td>
          <DisplayDate date={file.created_at} />
        </td>
      </tr>
      <tr>
        <th>Completed</th>
        <td>
          {file.completed_at ? (
            <DisplayDate date={file.completed_at} />
          ) : (
            <i>Incomplete!</i>
          )}
          {file.completed_at ? (
            <small>
              {' '}
              (took{' '}
              <DisplayDateDifference
                from={file.created_at}
                to={file.completed_at}
              />)
            </small>
          ) : null}
        </td>
      </tr>
    </tbody>
  </table>
)

export const ShowMicrosoftDownloadMetadata = ({ download }) => (
  <table className="table is-fullwidth">
    <tbody>
      <tr>
        <th>URL</th>
        <td>{download.url}</td>
      </tr>
      <tr>
        <th>Error</th>
        <td>
          {download.error ? (
            <span className="has-text-danger">{download.error}</span>
          ) : (
            '-'
          )}
        </td>
      </tr>
      <tr>
        <th>Created</th>
        <td>
          <DisplayDate date={download.created_at} />
        </td>
      </tr>
      <tr>
        <th>Completed</th>
        <td>
          {download.completed_at ? (
            <DisplayDate date={download.completed_at} />
          ) : (
            <i>Incomplete!</i>
          )}
          {download.completed_at ? (
            <small>
              {' '}
              (took{' '}
              <DisplayDateDifference
                from={download.created_at}
                to={download.completed_at}
              />)
            </small>
          ) : null}
        </td>
      </tr>
    </tbody>
  </table>
)

const capitalize = s => {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export class SortLink extends React.PureComponent {
  change = event => {
    event.preventDefault()
    const { current, name } = this.props
    let reverse = true
    if (current && current.sort === name) {
      reverse = !current.reverse
    }
    this.props.onChangeSort({
      sort: name,
      reverse: reverse
    })
  }
  render() {
    const { current, name } = this.props
    const title = this.props.title || capitalize(name)
    const currentUrl = document.location.pathname
    let isCurrent = false
    let isReverse = true
    if (current && current.sort === name) {
      isCurrent = true
      isReverse = current.reverse
    }
    let arrow
    if (isCurrent) {
      if (isReverse) {
        arrow = '⬇'
      } else {
        arrow = '⬆'
      }
    } else {
      arrow = '⇣'
    }
    return (
      <Link
        to={currentUrl}
        title={`Click to sort by ${title}`}
        onClick={this.change}
      >
        {arrow}
      </Link>
    )
  }
}
