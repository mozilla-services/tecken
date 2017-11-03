import React, { PureComponent } from 'react'
import { Link } from 'react-router-dom'

import { Loading, formatFileSize } from './Common'
import store from './Store'

export default class UploadNow extends PureComponent {
  constructor(props) {
    super(props)
    this.pageTitle = 'Symbol Upload Now'
    this.state = {
      loading: false
      // upload: null
    }
  }
  componentWillMount() {
    store.resetApiRequests()
  }

  componentDidMount() {
    document.title = this.pageTitle
  }

  render() {
    return (
      <div>
        <h1 className="title">{this.pageTitle}</h1>

        {store.hasPermission('upload.view_all_uploads') ? (
          <div className="tabs is-centered">
            <ul>
              <li>
                <Link to="/uploads" onClick={this.filterOnAll}>
                  All Uploads
                </Link>
              </li>
              <li>
                <Link to={`/uploads?user=${store.currentUser.email}`}>
                  Your Uploads
                </Link>
              </li>
              <li>
                <Link to="/uploads/files">All Files</Link>
              </li>
              <li className="is-active">
                <Link to="/uploads/upload">Upload Now</Link>
              </li>
            </ul>
          </div>
        ) : (
          <div className="tabs is-centered">
            <ul>
              <li>
                <Link to="/uploads">All Uploads</Link>
              </li>
              <li className="is-active">
                <Link to="/uploads/upload">Upload Now</Link>
              </li>
            </ul>
          </div>
        )}

        {this.state.loading && <Loading />}

        <div className="section">
          <div className="container">
            <h3 className="title is-3">Upload archive file via web</h3>
            <UploadForm />
          </div>
        </div>

        <div className="section">
          <div className="container">
            <h3 className="title is-3">Upload by download URL</h3>
            <UploadByDownloadForm />
          </div>
        </div>

        <div className="section">
          <div className="container">
            <h3 className="title is-3">Upload via command line</h3>
            <AboutCommandLineUpload />
          </div>
        </div>
      </div>
    )
  }
}

class AboutCommandLineUpload extends PureComponent {
  render() {
    return (
      <div>
        <p>
          To upload via the command line, you need an{' '}
          <Link to="/tokens">API Token</Link> that has the{' '}
          <code>Upload Symbol Files</code> permission attached to it.
        </p>

        <p>
          <a
            href="https://tecken.readthedocs.io/en/latest/upload.html#how-it-works"
            rel="noopener noreferrer"
          >
            Use the official documentation
          </a>{' '}
          for how to use <code>curl</code> or Python.
        </p>
      </div>
    )
  }
}

class UploadForm extends PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      loading: false,
      fileInfo: null,
      warning: null,
      validationError: null
    }
  }
  submitForm = event => {
    event.preventDefault()
    if (!this.filesInput.files.length) {
      return
    }
    const formData = new FormData()
    const file = this.filesInput.files[0]
    formData.append(file.name, file)
    this.setState({ loading: true, validationError: null })
    return fetch('/upload/', {
      method: 'POST',
      body: formData,
      credentials: 'same-origin'
    }).then(r => {
      if (store.fetchError) {
        store.fetchError = null
      }
      if (r.status === 201) {
        this.setState({
          loading: false,
          validationError: null,
          warning: null
        })
        r.json().then(data => {
          const upload = data.upload
          store.setRedirectTo(`/uploads/upload/${upload.id}`, {
            message: 'Symbols uploaded.',
            success: true
          })
        })
      } else if (r.status === 400) {
        r.json().then(data => {
          this.setState({
            loading: false,
            validationError: data.error,
            warning: null
          })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  onFileInputChange = event => {
    const file = this.filesInput.files[0]
    if (!/\.(zip|tar|tag\.gz)$/i.test(file.name)) {
      this.setState({
        warning: 'Make sure the file is a zip, tar.gz or tar file.'
      })
    } else if (this.state.warning) {
      this.setState({ warning: null })
    }
    this.setState({
      fileInfo: {
        name: file.name,
        size: file.size,
        type: file.type
      }
    })
  }

  render() {
    return (
      <form onSubmit={this.submitForm}>
        {this.state.validationError && (
          <article className="message is-danger">
            <div className="message-body">{this.state.validationError}</div>
          </article>
        )}
        <div className="field">
          <div className="file has-name is-fullwidth">
            <label className="file-label">
              <input
                className="file-input"
                type="file"
                name="archive"
                onChange={this.onFileInputChange}
                ref={input => {
                  this.filesInput = input
                }}
              />
              <span className="file-cta">
                <span className="file-icon">
                  <i className="fa fa-upload" />
                </span>
                <span className="file-label">Choose a file…</span>
              </span>

              <span className="file-name">
                {this.state.fileInfo ? (
                  <ShowFileInfo info={this.state.fileInfo} />
                ) : (
                  <i>no file selected yet</i>
                )}
              </span>
            </label>
          </div>
        </div>
        {this.state.warning && (
          <article className="message is-warning">
            <div className="message-body">{this.state.warning}</div>
          </article>
        )}
        <div className="field is-grouped">
          <p className="control">
            <button
              type="submit"
              className={
                this.state.loading
                  ? 'button is-primary is-loading'
                  : 'button is-primary'
              }
              disabled={this.state.loading}
            >
              Upload
            </button>
          </p>
          <p className="control">
            <Link to="/uploads" className="button is-light">
              Cancel
            </Link>
          </p>
        </div>
      </form>
    )
  }
}

const ShowFileInfo = ({ info }) => (
  <span>
    {info.name}{' '}
    <small>
      ({formatFileSize(info.size)} {info.type})
    </small>
  </span>
)

class UploadByDownloadForm extends UploadForm {
  constructor(props) {
    super(props)
    this.state = {
      url: null
    }
  }
  submitForm = event => {
    event.preventDefault()
    const url = this.refs.url.value.trim()
    if (!url) {
      return
    }
    const formData = new FormData()
    formData.append('url', url)
    this.setState({ loading: true, validationError: null })
    return fetch('/upload/', {
      method: 'POST',
      body: formData,
      credentials: 'same-origin'
    }).then(r => {
      if (store.fetchError) {
        store.fetchError = null
      }
      if (r.status === 201) {
        this.setState({
          loading: false,
          validationError: null,
          warning: null
        })
        r.json().then(data => {
          const upload = data.upload
          store.setRedirectTo(`/uploads/upload/${upload.id}`, {
            message: 'Symbols URL downloaded.',
            success: true
          })
        })
      } else if (r.status === 400) {
        r.json().then(data => {
          this.setState({
            loading: false,
            validationError: data.error,
            warning: null
          })
        })
      } else {
        store.fetchError = r
      }
    })
  }

  onFileInputChange = event => {
    const file = this.filesInput.files[0]
    if (!/\.(zip|tar|tag\.gz)$/i.test(file.name)) {
      this.setState({
        warning: 'Make sure the file is a zip, tar.gz or tar file.'
      })
    } else if (this.state.warning) {
      this.setState({ warning: null })
    }
    this.setState({ fileName: file.name })
  }

  render() {
    return (
      <form onSubmit={this.submitForm}>
        {this.state.validationError && (
          <article className="message is-danger">
            <div className="message-body">{this.state.validationError}</div>
          </article>
        )}
        <div className="field">
          <input
            className="input"
            type="text"
            placeholder="E.g. https://download.example.com/YYYYMMDD/symbols.zip"
            ref="url"
          />
          <p className="help">
            The upload by download is restricted to a whitelist of domains from
            which you can download.
          </p>
        </div>
        {this.state.warning && (
          <article className="message is-warning">
            <div className="message-body">{this.state.warning}</div>
          </article>
        )}
        <div className="field is-grouped">
          <p className="control">
            <button
              type="submit"
              className={
                this.state.loading
                  ? 'button is-primary is-loading'
                  : 'button is-primary'
              }
              disabled={this.state.loading}
            >
              Upload
            </button>
          </p>
          <p className="control">
            <Link to="/uploads" className="button is-light">
              Cancel
            </Link>
          </p>
        </div>
      </form>
    )
  }
}
