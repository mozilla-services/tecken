import React from 'react'
import { Link } from 'react-router-dom'

import {
  Loading,
  ShowUploadMetadata,
  ShowFileMetadata,
  ShowMicrosoftDownloadMetadata,
  BooleanIcon
} from './Common'
import Fetch from './Fetch'
import store from './Store'

export default class File extends React.PureComponent {
  constructor(props) {
    super(props)
    this.pageTitle = 'Symbol Upload File'
    this.state = {
      loading: false,
      file: null
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
    this._id = this.props.match.params.id
    this._fetchFile(this.props.match.params.id)
  }

  componentDidUpdate() {
    if (this._id !== this.props.match.params.id) {
      this._id = this.props.match.params.id
      this._fetchFile(this.props.match.params.id)
    }
  }

  goBack = event => {
    this.props.history.goBack()
  }

  _fetchFile = id => {
    this.setState({ loading: true })
    return Fetch(`/api/uploads/files/file/${id}`, {
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
          this.setState({ file: response.file })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  render() {
    return (
      <div>
        <h1 className="title">{this.pageTitle}</h1>
        <div className="is-clearfix">
          <p className="is-pulled-right">
            {this.props.history.action === 'PUSH' && (
              <a className="button is-small is-info" onClick={this.goBack}>
                <span className="icon">
                  <i className="fa fa-backward" />
                </span>{' '}
                <span>Back to Uploads</span>
              </a>
            )}
            {this.props.history.action === 'POP' && (
              <Link to="/uploads" className="button is-small is-info">
                <span className="icon">
                  <i className="fa fa-backward" />
                </span>{' '}
                <span>Back to Uploads</span>
              </Link>
            )}
          </p>
        </div>

        {this.state.loading && <Loading />}
        {this.state.file && <DisplayFile file={this.state.file} />}
      </div>
    )
  }
}

const stripPrefix = uri => {
  const parts = uri.split('/')
  parts[0] = ''
  return parts.join('/')
}

class DisplayFile extends React.PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      loading: true,
      headLoading: true,
      headSuccess: null
    }
  }

  headQuery = file => {
    const publicUrl = stripPrefix(file.key)
    fetch(publicUrl, { method: 'HEAD' }).then(r => {
      this.setState({ headSuccess: r.status === 200, headLoading: false })
    })
  }

  componentDidMount() {
    this.headQuery(this.props.file)
  }

  absoluteURL = () => {
    const uri = stripPrefix(this.props.file.key)
    let host = document.location.host
    if (host === 'localhost:3000') {
      // You're in the middle of local development, change this
      // for the sake of the developer.
      host = 'localhost:8000'
    }
    return `${document.location.protocol}//${host}${uri}`
  }

  render() {
    const { file } = this.props
    return (
      <div>
        <h4 className="title is-4">Public URL</h4>
        <p className="has-text-centered" style={{ marginBottom: 50 }}>
          <a href={this.absoluteURL()}>{this.absoluteURL()}</a>
          <br />
          {this.state.headLoading ? (
            <span className="icon">
              <i className="fa fa-spinner fa-spin fa-3x fa-fw" />
            </span>
          ) : (
            <span>
              {BooleanIcon(this.state.headSuccess)}
              {this.state.headSuccess ? 'Yep, it exists' : 'Sorry, not found'}
            </span>
          )}
        </p>

        <h4 className="title is-4">Metadata</h4>
        <ShowFileMetadata file={file} />

        {file.upload && (
          <h4 className="title is-4">
            <Link to={`/uploads/upload/${file.upload.id}`}>Upload</Link>
          </h4>
        )}
        {file.upload && (
          <h4 className="title subtitle">Upload It Was Part Of</h4>
        )}
        {file.upload && <ShowUploadMetadata upload={file.upload} />}

        {file.microsoft_download && (
          <h4 className="title is-4">Microsoft Download</h4>
        )}
        {file.microsoft_download && (
          <ShowMicrosoftDownloadMetadata download={file.microsoft_download} />
        )}
      </div>
    )
  }
}
