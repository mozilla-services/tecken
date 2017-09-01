import React, { Component } from 'react'
import { Link } from 'react-router-dom'

class Help extends Component {
  pageTitle = 'Help'
  componentDidMount() {
    document.title = 'Help'
  }
  render() {
    return (
      <div className="content">
        <h1 className="title">
          {this.pageTitle}
        </h1>
        <h2>Usage as a symbol server for Microsoft Debuggers</h2>
        <p>
          To use this as a symbol server for Microsoft debuggers, see{' '}
          <a href="https://developer.mozilla.org/en-US/docs/Mozilla/Using_the_Mozilla_symbol_server">
            this MDN article
          </a>{' '}
          for instructions on how to configure your debugger.
        </p>
        <h2>Permissions</h2>
        <p>
          To gain permissions to do things you need to be promoted by a
          superuser. <br />
          <a
            rel="noopener noreferrer"
            href="https://bugzilla.mozilla.org/enter_bug.cgi?product=Socorro&component=Symbols"
          >
            The best way to do that is to file a bug
          </a>.
        </p>

        <h2>API Tokens</h2>
        <p>
          To be able to do things like uploading symbols or querying what's
          already been uploaded, <i>outside</i> this web app, you can use{' '}
          <Link to="/tokens">API tokens</Link>.
        </p>

        <h2 id="upload-symbols-archives">Upload Symbols Archives</h2>
        <p>
          To upload symbols archives (<code>.zip</code> files full of symbol
          files) there are certain requirements:
        </p>
        <ul>
          <li>That you have the permission to upload symbols.</li>
          <li>
            That you have created a valid <Link to="/tokens">API token</Link>{' '}
            and associated it with the <code>Upload Symbols Files</code>{' '}
            permission.
          </li>
          <li>
            Inside the archive file, each symbol file is supposed to be in a
            directory that is the <b>module name</b> (e.g <code>xul.pdb</code>),
            and that directory should contain a directory that is the{' '}
            <b>debug ID</b> (e.g. <code>
              014BB0B098DC4244BCFC9F76ED2FA5302
            </code>) and in that directory the <b>symbol file</b> (e.g.{' '}
            <code>xul.sym</code>).
          </li>
          <li>
            Any other structures, except the above, will be rejected with a
            <code>400 Bad Request</code> error.
          </li>
          <li>
            The only exception is files like <code>foo-symbols.txt</code> which
            are accepted but not uploaded to S3 or logged.
          </li>
        </ul>
        <p>
          More information is available in the{' '}
          <a
            rel="noopener noreferrer"
            href="https://tecken.readthedocs.io/en/latest/upload.html#checks-and-validations"
          >
            main documentation on uploading
          </a>.
        </p>
      </div>
    )
  }
}

export default Help
