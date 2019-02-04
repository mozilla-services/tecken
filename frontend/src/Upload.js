import React from "react";
import { Link } from "react-router-dom";

import { differenceInMinutes, differenceInMilliseconds } from "date-fns";

import {
  Loading,
  DisplayDate,
  formatFileSize,
  formatSeconds,
  DisplayDateDifference,
  BooleanIcon,
  thousandFormat,
  DisplayFilesSummary,
  ShowUploadMetadata,
  parseISODate
} from "./Common";
import "./Upload.css";
import Fetch from "./Fetch";
import store from "./Store";

export default class Upload extends React.PureComponent {
  constructor(props) {
    super(props);
    this.pageTitle = "Symbol Upload";
    this.state = {
      loading: true,
      upload: null,
      refreshingInterval: null
    };

    this.initialRefreshingInterval = 4;
  }
  componentWillMount() {
    store.resetApiRequests();
  }

  componentWillUnmount() {
    this.dismounted = true;
  }

  componentDidMount() {
    document.title = this.pageTitle;
    this.setState({ loading: true });
    this._upload_id = this.props.match.params.id;
    this._fetchUpload(this.props.match.params.id);
  }

  componentDidUpdate() {
    if (this._upload_id !== this.props.match.params.id) {
      this._upload_id = this.props.match.params.id;
      this._fetchUpload(this.props.match.params.id);
    }
  }

  goBack = event => {
    event.preventDefault();
    this.props.history.goBack();
  };

  _fetchUpload = id => {
    return Fetch(`/api/uploads/upload/${id}`, {
      credentials: "same-origin"
    }).then(r => {
      if (this.dismounted) {
        return;
      }
      this.setState({ loading: false });
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
        return r.json().then(response => {
          this.setState(
            {
              upload: response.upload,
              loading: false
            },
            () => {
              if (this.recentAndIncompleteUpload()) {
                this.keepRefreshing();
              } else if (this.state.refreshingInterval) {
                this.setState({ refreshingInterval: null });
              }
            }
          );
        });
      } else {
        store.fetchError = r;
      }
    });
  };

  keepRefreshing = () => {
    let refreshingInterval = this.state.refreshingInterval;
    if (!refreshingInterval) {
      refreshingInterval = this.initialRefreshingInterval;
    } else {
      refreshingInterval *= 1.5;
    }
    if (!this.dismounted) {
      window.setTimeout(() => {
        if (this.dismounted) {
          return;
        }
        if (this.state.upload) {
          this._fetchUpload(this.state.upload.id);
        }
      }, refreshingInterval * 1000);
      this.setState({
        refreshingInterval: refreshingInterval
      });
    }
  };

  refreshUpload = event => {
    event.preventDefault();
    this.setState({
      loading: true,
      refreshingInterval: this.initialRefreshingInterval
    });
    this._fetchUpload(this.state.upload.id);
  };

  recentAndIncompleteUpload = () => {
    if (!this.state.upload.completed_at) {
      const dateObj = parseISODate(this.state.upload.created_at);
      return differenceInMinutes(new Date(), dateObj) < 3;
    }
    return false;
  };

  render() {
    return (
      <div>
        <h1 className="title">{this.pageTitle}</h1>
        <div className="is-clearfix">
          <p className="is-pulled-right">
            {this.props.history.action === "PUSH" && (
              <Link
                to="/uploads"
                className="button is-small is-info"
                onClick={this.goBack}
              >
                <span className="icon">
                  <i className="fa fa-backward" />
                </span>{" "}
                <span>Back to Uploads</span>
              </Link>
            )}
            {this.props.history.action === "POP" && (
              <Link to="/uploads" className="button is-small is-info">
                <span className="icon">
                  <i className="fa fa-backward" />
                </span>{" "}
                <span>Back to Uploads</span>
              </Link>
            )}
          </p>
        </div>

        {this.state.loading && <Loading />}
        {this.state.upload &&
          !this.state.loading &&
          this.recentAndIncompleteUpload() && (
            <p className="is-pulled-right">
              <button
                className="button is-small is-primary"
                onClick={this.refreshUpload}
              >
                <span className="icon">
                  <i className="fa fa-refresh" />
                </span>{" "}
                <span>Refresh</span>
              </button>
            </p>
          )}
        {this.state.upload && this.state.refreshingInterval && (
          <DisplayRefreshingInterval interval={this.state.refreshingInterval} />
        )}
        {this.state.upload && <DisplayUpload upload={this.state.upload} />}
      </div>
    );
  }
}

class DisplayRefreshingInterval extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = { seconds: this._roundInterval(props.interval) };
  }
  _roundInterval = interval => Math.round(Number(interval));
  componentWillUnmount() {
    this.dismounted = true;
  }
  componentWillReceiveProps(nextProps) {
    this.setState({ seconds: this._roundInterval(nextProps.interval) });
  }
  componentDidMount() {
    this.loop = window.setInterval(() => {
      if (this.dismounted) {
        window.clearInterval(this.loop);
      } else {
        this.setState(state => {
          return { seconds: state.seconds - 1 };
        });
      }
    }, 1000);
  }
  render() {
    if (this.state.seconds <= 0) {
      return (
        <div className="tags">
          <span className="tag">Refreshing now</span>
        </div>
      );
    }
    let prettyTime = `${this.state.seconds} s`;
    if (this.state.seconds >= 60) {
      const minutes = Math.floor(this.state.seconds / 60);
      prettyTime = `${minutes} m`;
    }
    return (
      <div className="tags has-addons">
        <span className="tag">Refreshing in</span>
        <span className="tag is-primary">{prettyTime}</span>
      </div>
    );
  }
}

const DisplayUpload = ({ upload }) => {
  return (
    <div>
      <h4 className="title is-4">Metadata</h4>
      <ShowUploadMetadata upload={upload} />
      <ShowUploadFiles upload={upload} />

      {/* <h4 className="title is-4">Files Summary</h4> */}
      <ShowAggregates upload={upload} />
      <ShowUploadTimes upload={upload} />
      <ShowRelatedUploads upload={upload} />
    </div>
  );
};

/* Return a new array where every item is an object.
   The reason we do this is because an upload consists of a pure array
   of skipped keys, a pure array of ignored keys and an array of
   file upload objects.
*/
const mergeAllKeys = (uploads, skipped, ignored) => {
  const all = [];
  ignored.forEach(key => {
    all.push({ key: key, ignored: true });
  });
  skipped.forEach(key => {
    all.push({ key: key, skipped: true });
  });
  uploads.forEach(upload => {
    all.push(upload);
  });
  return all;
};

class ShowUploadFiles extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      sortBy: null,
      reverse: false
    };
  }

  _sortByKey = (key, defaultReverse = false) => {
    if (this.state.sortBy === key) {
      this.setState({ reverse: !this.state.reverse });
    } else {
      this.setState({ sortBy: key, reverse: defaultReverse });
    }
  };

  sortByKey = event => {
    event.preventDefault();
    this._sortByKey("key");
  };

  sortBySize = event => {
    event.preventDefault();
    this._sortByKey("size", true);
  };

  sortByUpdate = event => {
    event.preventDefault();
    this._sortByKey("update");
  };

  sortByCompressed = event => {
    event.preventDefault();
    this._sortByKey("compressed");
  };

  sortByTime = event => {
    event.preventDefault();
    this._sortByKey("time", true);
  };

  sortKeys = keys => {
    if (!this.state.sortBy) {
      return keys;
    }
    const sortBy = this.state.sortBy;
    const reverse = this.state.reverse ? -1 : 1;

    const cmp = (a, b) => {
      if (a > b) {
        return 1 * reverse;
      } else if (a < b) {
        return -1 * reverse;
      }
    };
    keys.sort((a, b) => {
      if (sortBy === "key") {
        return cmp(a.key.toLowerCase(), b.key.toLowerCase());
      } else if (sortBy === "time") {
        return cmp(a._time || 0, b._time || 0);
      }
      return cmp(a[sortBy] || 0, b[sortBy] || 0);
    });
    return keys;
  };

  _addTime = files => {
    return files.map(file => {
      if (file.completed_at) {
        file._time = differenceInMilliseconds(
          parseISODate(file.completed_at),
          parseISODate(file.created_at)
        );
      }
      return file;
    });
  };

  render() {
    const { upload } = this.props;
    const allKeys = this.sortKeys(
      mergeAllKeys(
        this._addTime(upload.file_uploads),
        upload.skipped_keys,
        upload.ignored_keys
      )
    );
    return (
      <div>
        <h4 className="title is-4">Files</h4>
        <table className="table is-fullwidth files-table">
          <thead>
            <tr>
              <th className="sortable" onClick={this.sortByKey}>
                Key
              </th>
              <th className="sortable" onClick={this.sortBySize}>
                Size
              </th>
              <th
                className="bool-row sortable"
                title="True if the file overwrote an existing one with the same name"
                onClick={this.sortByUpdate}
              >
                Update
              </th>
              <th
                className="bool-row"
                title="True if the file was first gzipped before uploading"
                onClick={this.sortByCompressed}
              >
                Compressed
              </th>
              <th className="sortable" onClick={this.sortByTime}>
                Time to complete
              </th>
            </tr>
          </thead>
          <tbody>
            {allKeys.map(file => {
              if (file.skipped || file.ignored) {
                return (
                  <tr key={file.key}>
                    <td className="file-key">{file.key}</td>
                    <td colSpan={6}>
                      <b>{file.skipped ? "Skipped" : "Ignored"}</b>{" "}
                      {file.skipped ? (
                        <small>
                          Not uploaded because existing file has the same size
                        </small>
                      ) : (
                        <small>
                          File OK in the archive but deliberately not uploaded
                        </small>
                      )}
                    </td>
                  </tr>
                );
              }
              return (
                <tr key={file.key}>
                  <td className="file-key">
                    <Link to={`/uploads/files/file/${file.id}`}>
                      {file.key}
                    </Link>
                  </td>
                  <td>{formatFileSize(file.size)}</td>
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
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }
}

const ShowAggregates = ({ upload }) => {
  const fileSizes = upload.file_uploads.map(u => u.size);
  const filesSizeSum = fileSizes.reduce((a, b) => a + b, 0);
  let filesSizeAvg = null;
  if (fileSizes.length) {
    filesSizeAvg = filesSizeSum / fileSizes.length;
  }
  return (
    <nav className="level" style={{ marginTop: 60 }}>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Files Uploaded</p>
          <p className="title">{thousandFormat(upload.file_uploads.length)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Files Sizes Sum</p>
          <p className="title">{formatFileSize(filesSizeSum)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Files Sizes Avg</p>
          <p className="title">
            {filesSizeAvg ? formatFileSize(filesSizeAvg) : "n/a"}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p
            className="heading"
            title="Files with the uploads we know we can skip"
          >
            Skipped Files
          </p>
          <p className="title">{thousandFormat(upload.skipped_keys.length)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading" title="Files we can safely ignore">
            Ignored Files
          </p>
          <p className="title">{thousandFormat(upload.ignored_keys.length)}</p>
        </div>
      </div>
    </nav>
  );
};

const ShowUploadTimes = ({ upload }) => {
  if (!upload.completed_at) {
    return null;
  }
  const uploadStart = parseISODate(upload.created_at);
  const uploadEnd = parseISODate(upload.completed_at);
  const uploadTime = differenceInMilliseconds(uploadEnd, uploadStart);
  const uploadTimes = [];
  let longestFileUpload = null;
  upload.file_uploads.forEach(file => {
    if (file.completed_at) {
      const start = parseISODate(file.created_at);
      const end = parseISODate(file.completed_at);
      const diff = differenceInMilliseconds(end, start);
      if (longestFileUpload === null || longestFileUpload < diff) {
        longestFileUpload = diff;
      }
      uploadTimes.push(diff);
    }
  });
  if (!uploadTimes.length) {
    return null;
  }

  const filesSum = uploadTimes.reduce((a, b) => a + b, 0);
  const filesAvg = filesSum / uploadTimes.length;
  uploadTimes.sort((a, b) => a - b);
  const filesMedian =
    (uploadTimes[(uploadTimes.length - 1) >> 1] +
      uploadTimes[uploadTimes.length >> 1]) /
    2;

  return (
    <nav className="level" style={{ marginTop: 60 }}>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Total Completion Time</p>
          <p className="title">{formatSeconds(uploadTime / 1000)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Sum File Upload Time</p>
          <p className="title">{formatSeconds(filesSum / 1000)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Average File Upload Time</p>
          <p className="title">{formatSeconds(filesAvg / 1000)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Median File Upload Time</p>
          <p className="title">{formatSeconds(filesMedian / 1000)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Longest File Upload Time</p>
          <p className="title">{formatSeconds(longestFileUpload / 1000)}</p>
        </div>
      </div>
    </nav>
  );
};

const ShowRelatedUploads = ({ upload }) => {
  if (!upload.related.length) {
    return null;
  }
  return (
    <div style={{ marginTop: 100 }}>
      <h4 className="title is-4">Related Uploads ({upload.related.length})</h4>
      <table className="table">
        <thead>
          <tr>
            <th>Files</th>
            <th>Uploaded</th>
            <th>Completed</th>
          </tr>
        </thead>
        <tbody>
          {upload.related.map(upload => (
            <ShowUploadRow key={upload.id} upload={upload} />
          ))}
        </tbody>
      </table>
    </div>
  );
};

const ShowUploadRow = ({ upload }) => {
  return (
    <tr>
      <td>
        <Link
          to={`/uploads/upload/${upload.id}`}
          title="Click to see detailed information about this upload"
          onClick={event => window.scroll(0, 0)}
        >
          {DisplayFilesSummary(
            upload.file_uploads.filter(x => x.completed_at).length,
            upload.file_uploads.filter(x => !x.completed_at).length,
            upload.skipped_keys.length,
            upload.ignored_keys.length
          )}
        </Link>
      </td>
      <td>
        <DisplayDate date={upload.created_at} />
      </td>
      <td>
        {upload.completed_at ? (
          <DisplayDateDifference
            from={upload.created_at}
            to={upload.completed_at}
            suffix="after"
          />
        ) : (
          <i>Incomplete!</i>
        )}
      </td>
    </tr>
  );
};
