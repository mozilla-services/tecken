/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */
import React from "react";
import { Link } from "react-router-dom";
import { format } from "date-fns";

import {
  Loading,
  DisplayDate,
  formatFileSize,
  Pagination,
  BooleanIcon,
  TableSubTitle,
  FilterSummary,
  thousandFormat,
  formatSeconds,
  DisplayDateDifference,
  filterToQueryString,
  parseQueryString,
} from "./Common";
import Fetch from "./Fetch";
import "./Upload.css"; // they have enough in common
import "./Files.css";

import store from "./Store";

class Files extends React.PureComponent {
  constructor(props) {
    super(props);
    this.pageTitle = "All Files";
    this.state = {
      loadingFiles: true, // undone by componentDidMount
      files: null,
      hasNextPage: false,
      total: null,
      batchSize: null,
      apiUrl: null,
      filter: {
        // We want the filter for created_at to default to the last 30 days
        created_at: this.getThirtyDaysFilterValue(),
      },
    };
  }

  getThirtyDaysFilterValue() {
    var thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    return ">=" + format(thirtyDaysAgo, "yyyy-MM-dd");
  }

  componentWillMount() {
    store.resetApiRequests();
  }

  componentDidMount() {
    document.title = this.pageTitle;
    if (this.props.location.search) {
      this.setState(
        { filter: parseQueryString(this.props.location.search) },
        () => {
          this._fetchFiles(false);
        }
      );
    } else {
      this._fetchFiles(false);
    }
  }

  _fetch = (url, callback, errorCallback, updateHistory = true) => {
    const qs = filterToQueryString(this.state.filter);

    if (qs) {
      url += "?" + qs;
    }
    this.props.history.push({ search: qs });

    Fetch(url).then((r) => {
      if (this.setLoadingTimer) {
        window.clearTimeout(this.setLoadingTimer);
      }
      if (r.status === 403 && !store.currentUser) {
        store.setRedirectTo(
          "/",
          `You have to be signed in to view "${this.pageTitle}"`
        );
        return;
      }
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null;
        }
        return r.json().then((response) => callback(response));
      } else {
        store.fetchError = r;
        if (errorCallback) {
          errorCallback();
        }
      }
    });
  };

  _fetchFiles = (updateHistory = true) => {
    var callback = (response) => {
      this.setState({
        loadingFiles: false,
        total: response.total,
        files: response.files,
        hasNextPage: response.has_next,
        batchSize: response.batch_size,
      });
    };
    var errorCallback = () => {
      this.setState({ loadingFiles: false });
    };
    this.setState({ loadingFiles: true });
    this._fetch("/api/uploads/files/", callback, errorCallback, updateHistory);
  };

  filterOnAll = (event) => {
    event.preventDefault();
    const filter = this.state.filter;
    // delete filter.user
    delete filter.download;
    filter.page = 1;
    filter.key = "";
    filter.size = "";
    this.setState({ filter: filter }, this._fetchFiles);
  };

  updateFilter = (newFilters) => {
    this.setState(
      {
        filter: Object.assign({}, this.state.filter, newFilters),
      },
      this._fetchFiles
    );
  };

  render() {
    const todayStr = format(new Date(), "yyyy-MM-dd");
    const todayFullStr = format(new Date(), "yyyy-MM-ddTHH:MM.SSS'Z'");
    return (
      <div>
        {store.hasPermission("upload.view_all_uploads") ? (
          <div className="tabs is-centered">
            <ul>
              <li className={!this.state.filter.download ? "is-active" : ""}>
                <Link to="/uploads/files" onClick={this.filterOnAll}>
                  All Files
                </Link>
              </li>
              <li>
                <Link to="/uploads">All Uploads</Link>
              </li>
            </ul>
          </div>
        ) : null}
        <h1 className="title">{this.pageTitle}</h1>

        {this.state.loadingFiles ? (
          <Loading />
        ) : (
          this.state.files && (
            <TableSubTitle
              total={this.state.total}
              page={this.state.filter.page}
              batchSize={this.state.batchSize}
              calculating={this.state.loadingFiles}
            />
          )
        )}

        <FilterSummary filter={this.state.filter} />

        {!this.state.loadingFiles && this.state.files && (
          <DisplayFiles
            loading={this.state.loadingFiles}
            files={this.state.files}
            batchSize={this.state.batchSize}
            location={this.props.location}
            filter={this.state.filter}
            updateFilter={this.updateFilter}
            hasNextPage={this.state.hasNextPage}
          />
        )}

        <ExamplesOfFiltering todayStr={todayStr} todayFullStr={todayFullStr} />
      </div>
    );
  }
}

export default Files;

class DisplayFiles extends React.PureComponent {
  componentDidMount() {
    // XXX perhaps this stuff should happen in a componentWillReceiveProps too
    const filter = this.props.filter;
    this.refs.key.value = filter.key || "";
    this.refs.size.value = filter.size || "";
    this.refs.upload_type.value = filter.upload_type || "";
    this.refs.created_at.value = filter.created_at || "";
    this.refs.bucketName.value = filter.bucket_name || "";
  }

  submitForm = (event) => {
    event.preventDefault();
    const key = this.refs.key.value.trim();
    const size = this.refs.size.value.trim();
    const upload_type = this.refs.upload_type.value.trim();
    const created_at = this.refs.created_at.value.trim();
    const bucketName = this.refs.bucketName.value.trim();
    this.props.updateFilter({
      page: 1,
      key,
      size,
      created_at,
      bucket_name: bucketName,
      upload_type: upload_type,
    });
  };

  resetFilter = (event) => {
    this.refs.key.value = "";
    this.refs.size.value = "";
    this.refs.bucketName.value = "";
    this.refs.upload_type.value = "";
    this.refs.created_at.value = "";
    this.submitForm(event);
  };
  render() {
    const { loading, files } = this.props;

    return (
      <form onSubmit={this.submitForm}>
        <table className="table is-fullwidth is-narrow files-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Size</th>
              <th>Bucket</th>
              <th>Upload type</th>
              <th>Uploaded</th>
              <th
                className="bool-row is-clipped"
                title="True if the file overwrote an existing one with the same name"
              >
                Update
              </th>
              <th
                className="bool-row is-clipped"
                title="True if the file was first gzipped before uploading"
              >
                Compressed
              </th>
              <th>Time to complete</th>
            </tr>
          </thead>

          <tfoot>
            <tr>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="key"
                  placeholder="filter key ..."
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="size"
                  placeholder="filter size ..."
                  style={{ width: 140 }}
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="bucketName"
                  placeholder="filter bucket ..."
                  style={{ width: 140 }}
                />
              </td>
              <td>
                <span className="select">
                  <select name="upload_type" ref="upload_type">
                    <option></option>
                    <option>regular</option>
                    <option>try</option>
                  </select>
                </span>
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="created_at"
                  placeholder="filter uploaded ..."
                  style={{ width: 140 }}
                />
              </td>
              <td colSpan={3} style={{ minWidth: 230 }}>
                <button type="submit" className="button is-primary">
                  Filter
                </button>{" "}
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
            {!loading &&
              files.map((file) => (
                <tr key={file.id}>
                  <td className="file-key">
                    <Link to={`/uploads/files/file/${file.id}`}>
                      {file.key}
                    </Link>
                  </td>
                  <td>{formatFileSize(file.size)}</td>
                  <td>{file.bucket_name}</td>
                  <td>
                    {file.upload && file.upload.upload_type === "try" ? (
                      <span className="tag is-info" title="try symbol upload">
                        try
                      </span>
                    ) : (
                      <span
                        className="tag"
                        title="{file.upload.upload_type} symbol upload"
                      >
                        {file.upload.upload_type}
                      </span>
                    )}
                  </td>
                  <td>
                    {file.upload ? (
                      <Link
                        to={`/uploads/upload/${file.upload.id}`}
                        title={`Uploaded by ${file.upload.user.email}`}
                      >
                        <DisplayDate date={file.created_at} />
                      </Link>
                    ) : (
                      <DisplayDate date={file.created_at} />
                    )}{" "}
                  </td>
                  <td>{BooleanIcon(file.update)}</td>
                  <td>{BooleanIcon(file.compressed)}</td>
                  <td>
                    {file.completed_at ? (
                      <DisplayDateDifference
                        from={file.created_at}
                        to={file.completed_at}
                      />
                    ) : (
                      <i>Incomplete!</i>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>

        {!loading && (
          <Pagination
            location={this.props.location}
            total={this.props.total}
            batchSize={this.props.batchSize}
            updateFilter={this.props.updateFilter}
            currentPage={this.props.filter.page}
            hasNext={this.props.hasNextPage}
          />
        )}
      </form>
    );
  }
}

const ExamplesOfFiltering = ({ todayStr, todayFullStr }) => (
  <article className="message" style={{ marginTop: 50 }}>
    <div className="message-header">
      <p>Examples of Filtering</p>
      {/* <button className="delete" aria-label="delete" /> */}
      {/* <button className="button is-small">open</button> */}
    </div>
    <div className="message-body">
      <ul>
        <li>
          <b>Key:</b> <code>xul.pdb</code> to filter all files with "xul.pdb" in
          the key.
        </li>
        <li>
          <b>Size:</b> <code>&gt;1mb</code> to filter all files <i>bigger</i>{" "}
          than one megabyte.
        </li>
        <li>
          <b>Bucket:</b> <code>publicbucket</code> to filter files put in the
          public bucket.
        </li>
        <li>
          <b>Uploaded:</b> <code>{todayStr}</code> to filter all files uploaded
          any time during this day (in UTC).
        </li>
        <li>
          <b>Uploaded:</b>{" "}
          <code>
            &gt;=
            {todayFullStr}
          </code>{" "}
          to filter all files uploaded after this ISO date (in UTC).
        </li>
        <li>
          <b>Uploaded:</b> <code>today</code> (or <code>yesterday</code>) to
          filter all files uploaded after yesterday's UTC daybreak.
        </li>
      </ul>
    </div>
  </article>
);
