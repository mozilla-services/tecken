import React from "react";
import { Link } from "react-router-dom";

import {
  Loading,
  DisplayDate,
  formatFileSize,
  Pagination,
  BooleanIcon,
  TableSubTitle,
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
      loading: true, // undone by componentDidMount
      files: null,
      total: null,
      batchSize: null,
      apiUrl: null,
      filter: {},
    };
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

  _fetchFiles = (updateHistory = true) => {
    // delay the loading animation in case it loads really fast
    this.setLoadingTimer = window.setTimeout(() => {
      this.setState({ loading: true });
    }, 500);
    let url = "/api/uploads/files/";
    const qs = filterToQueryString(this.state.filter);
    if (qs) {
      url += "?" + qs;
    }
    this.props.history.push({ search: qs });

    Fetch(url, { credentials: "same-origin" }).then((r) => {
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
      this.setState({ loading: false });
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null;
        }
        return r.json().then((response) => {
          this.setState({
            files: response.files,
            aggregates: response.aggregates,
            total: response.total,
            batchSize: response.batch_size,
          });
        });
      } else {
        store.fetchError = r;
      }
    });
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

  filterOnMicrosoftDownloads = (event) => {
    event.preventDefault();
    const filter = this.state.filter;
    filter.download = "microsoft";
    filter.page = 1;
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
              <li
                className={
                  this.state.filter.download === "microsoft" ? "is-active" : ""
                }
              >
                <Link
                  to="/uploads/files?download=microsoft"
                  onClick={this.filterOnMicrosoftDownloads}
                >
                  Microsoft Download Files
                </Link>
              </li>
              <li>
                <Link to="/uploads">All Uploads</Link>
              </li>
            </ul>
          </div>
        ) : null}
        <h1 className="title">{this.pageTitle}</h1>

        {this.state.loading ? (
          <Loading />
        ) : (
          <TableSubTitle
            total={this.state.total}
            page={this.state.filter.page}
            batchSize={this.state.batchSize}
          />
        )}

        {this.state.files && (
          <DisplayFiles
            loading={this.state.loading}
            files={this.state.files}
            aggregates={this.state.aggregates}
            total={this.state.total}
            batchSize={this.state.batchSize}
            location={this.props.location}
            filter={this.state.filter}
            updateFilter={this.updateFilter}
          />
        )}
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
    this.refs.created_at.value = filter.created_at || "";
    this.refs.bucketName.value = filter.bucket_name || "";
  }

  submitForm = (event) => {
    event.preventDefault();
    const key = this.refs.key.value.trim();
    const size = this.refs.size.value.trim();
    const created_at = this.refs.created_at.value.trim();
    const bucketName = this.refs.bucketName.value.trim();
    this.props.updateFilter({
      page: 1,
      key,
      size,
      created_at,
      bucket_name: bucketName,
    });
  };

  resetFilter = (event) => {
    this.refs.key.value = "";
    this.refs.size.value = "";
    this.refs.bucketName.value = "";
    this.refs.created_at.value = "";
    this.submitForm(event);
  };
  render() {
    const { loading, files, aggregates } = this.props;

    return (
      <form onSubmit={this.submitForm}>
        <table className="table is-fullwidth is-narrow files-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Size</th>
              <th>Bucket</th>
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
                  placeholder="filter..."
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="size"
                  placeholder="filter..."
                  style={{ width: 140 }}
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="bucketName"
                  placeholder="filter..."
                  style={{ width: 140 }}
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="created_at"
                  placeholder="filter..."
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
                    {file.upload && file.upload.try_symbols ? (
                      <span
                        className="tag is-info"
                        title="Part of a Try build upload"
                      >
                        Try
                      </span>
                    ) : null}
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
          />
        )}

        {!loading && <ShowAggregates aggregates={aggregates} />}
      </form>
    );
  }
}

const ShowAggregates = ({ aggregates }) => {
  return (
    <nav className="level" style={{ marginTop: 60 }}>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Files</p>
          <p className="title">
            {aggregates.files.count
              ? thousandFormat(aggregates.files.count)
              : "n/a"}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div title="Files that got started upload but never finished for some reason">
          <p className="heading">Incomplete Files</p>
          <p className="title">{thousandFormat(aggregates.files.incomplete)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">File Sizes Sum</p>
          <p className="title">
            {aggregates.files.size.sum
              ? formatFileSize(aggregates.files.size.sum)
              : "n/a"}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">File Sizes Avg</p>
          <p className="title">
            {aggregates.files.size.average
              ? formatFileSize(aggregates.files.size.average)
              : "n/a"}
          </p>
        </div>
      </div>
      <div
        className="level-item has-text-centered"
        title="Average time to complete upload of completed files"
      >
        <div>
          <p className="heading">Upload Time Avg</p>
          <p className="title">
            {aggregates.files.time.average
              ? formatSeconds(aggregates.files.time.average)
              : "n/a"}
          </p>
        </div>
      </div>
    </nav>
  );
};
