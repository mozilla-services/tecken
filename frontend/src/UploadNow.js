/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */
import React, { PureComponent } from "react";
import { Link } from "react-router-dom";

import store from "./Store";

export default class UploadNow extends PureComponent {
  constructor(props) {
    super(props);
    this.pageTitle = "Symbol Upload Now";
    this.state = {
      loading: false,
    };
  }

  componentWillMount() {
    store.resetApiRequests();
  }

  componentDidMount() {
    document.title = this.pageTitle;
  }

  render() {
    return (
      <div>
        <h1 className="title">{this.pageTitle}</h1>

        {store.hasPermission("upload.view_all_uploads") ? (
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

        <div className="section">
          <div className="container">
            <h3 className="title is-3">Upload via command line</h3>
            <AboutCommandLineUpload />
          </div>
        </div>
      </div>
    );
  }
}

class AboutCommandLineUpload extends PureComponent {
  render() {
    return (
      <div>
        <p>
          To upload via the command line, you need an{" "}
          <Link to="/tokens">API Token</Link> that has the{" "}
          <code>Upload Symbols Files</code> (or{" "}
          <code>Upload Try Symbols Files</code>) permission attached to it.
        </p>

        <p>
          <a
            href="https://tecken.readthedocs.io/en/latest/upload.html"
            rel="noopener noreferrer"
          >
            Use the official documentation
          </a>{" "}
          for how to use <code>curl</code> or Python.
        </p>
      </div>
    );
  }
}
