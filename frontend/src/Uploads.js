import React from "react";
import { Link } from "react-router-dom";
import { format } from "date-fns";

import {
  Loading,
  DisplayDate,
  DisplayDateDifference,
  formatFileSize,
  Pagination,
  TableSubTitle,
  thousandFormat,
  pluralize,
  DisplayFilesSummary,
  ShowValidationErrors,
  filterToQueryString,
  parseQueryString,
  SortLink
} from "./Common";
import Fetch from "./Fetch";
import "./Uploads.css";

import store from "./Store";

class Uploads extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      pageTitle: "Uploads",
      loading: true,
      refreshing: false,
      uploads: null,
      total: null,
      batchSize: null,
      apiUrl: null,
      filter: {},
      validationErrors: null,
      latestUpload: null,
      newUploadsCount: 0,
      orderBy: null
    };

    this.newCountLoopInterval = 5 * 1000;
  }

  componentWillMount() {
    store.resetApiRequests();
  }

  componentWillUnmount() {
    this.dismounted = true;
  }

  componentDidMount() {
    document.title = this.state.pageTitle;
    if (this.props.location.search) {
      this.setState(
        { filter: parseQueryString(this.props.location.search) },
        () => {
          // If you load the page with some filtering, the "latestUpload"
          // might not be the unfiltered latest upload.
          this._fetchAbsoluteLatestUpload().then(() => {
            this._fetchUploads();
          });
        }
      );
    } else {
      this._fetchUploads();
    }

    window.setTimeout(() => {
      this._fetchUploadsNewCountLoop();
    }, this.newCountLoopInterval);
  }

  _fetchUploads = () => {
    // delay the loading animation in case it loads really fast
    this.setLoadingTimer = window.setTimeout(() => {
      if (!this.dismounted) {
        this.setState({ loading: true });
      }
    }, 1000);
    let url = "/api/uploads/";
    const qs = filterToQueryString(this.state.filter, this.state.orderBy);
    if (qs) {
      url += "?" + qs;
    }
    this.props.history.push({ search: qs });

    return Fetch(url, { credentials: "same-origin" }).then(r => {
      if (this.setLoadingTimer) {
        window.clearTimeout(this.setLoadingTimer);
      }
      if (r.status === 403 && !store.currentUser) {
        store.setRedirectTo(
          "/",
          `You have to be signed in to view "${this.pageTitle}"`
        );
        // Even though we exit early, always return a promise
        return Promise.resolve();
      }
      this.setState({ loading: false, refreshing: false });
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null;
        }
        return r.json().then(response => {
          this.setState(
            {
              uploads: response.uploads,
              canViewAll: response.can_view_all,
              aggregates: response.aggregates,
              total: response.total,
              batchSize: response.batch_size,
              orderBy: response.order_by,
              validationErrors: null,
              latestUpload: this._getLatestUpload(response.uploads)
            },
            () => {
              if (this.state.newUploadsCount) {
                document.title = this.state.pageTitle;
                this.setState({ newUploadsCount: 0 });
              }
            }
          );
        });
      } else if (r.status === 400) {
        return r.json().then(data => {
          this.setState({
            loading: false,
            refreshing: false,
            validationErrors: data.errors
          });
        });
      } else {
        store.fetchError = r;
        // Always return a promise
        return Promise.resolve();
      }
    });
  };

  _fetchAbsoluteLatestUpload = () => {
    const url = "/api/uploads/";
    return fetch(url, { credentials: "same-origin" }).then(r => {
      if (r.status === 200) {
        return r.json().then(response => {
          return this.setState({
            latestUpload: this._getLatestUpload(response.uploads)
          });
        });
      }
    });
  };

  _refreshUploads = () => {
    this.setState({ refreshing: true });
    this._fetchUploads();
  };

  // This is called every time _fetchUploads() finishes successfully.
  _getLatestUpload = uploads => {
    // Of all 'uploads', look for the one with the highest
    // created_at and if it's more than this.state.latestUpload, update.
    let latestUpload = this.state.latestUpload;
    uploads.forEach(upload => {
      const createdAt = upload.created_at;
      if (latestUpload === null || createdAt > latestUpload) {
        latestUpload = createdAt;
      }
    });
    return latestUpload;
  };

  _fetchUploadsNewCountLoop = () => {
    if (!this.dismounted) {
      let url = "/api/uploads/";
      const qs = filterToQueryString(this.state.filter, {
        created_at: `>${this.state.latestUpload}`
      });
      url += "?" + qs;
      if (this.previousLatestUpload) {
        // assert that this time it's >= the previous one
        if (this.state.latestUpload < this.previousLatestUpload) {
          throw new Error("Bad state! Previous latestUpload has regressed");
        }
      }
      this.previousLatestUpload = this.state.latestUpload;
      // Not going to obsess over fetch errors
      Fetch(url, { credentials: "same-origin" }).then(r => {
        if (r.status === 200) {
          r.json().then(response => {
            if (response.total) {
              document.title = `(${response.total} new) ${this.state.pageTitle}`;
              this.setState({ newUploadsCount: response.total });
            }
            window.setTimeout(() => {
              this._fetchUploadsNewCountLoop();
            }, this.newCountLoopInterval);
          });
        } else {
          console.warn(`Unable to continue loop because of status ${r.status}`);
        }
      });
    }
  };

  filterOnAll = event => {
    event.preventDefault();
    const filter = this.state.filter;
    delete filter.user;
    this.setState({ filter: filter }, this._fetchUploads);
  };

  filterOnYours = event => {
    event.preventDefault();
    const filter = this.state.filter;
    filter.user = store.currentUser.email;
    this.setState({ filter: filter }, this._fetchUploads);
  };

  updateFilter = newFilters => {
    this.setState(
      {
        filter: Object.assign({}, this.state.filter, newFilters)
      },
      this._fetchUploads
    );
  };

  resetAndReload = event => {
    event.preventDefault();
    this.setState({ filter: {}, validationErrors: null }, () => {
      this._fetchUploads();
    });
  };

  _filterOnYourUploads = () => {
    if (this.state.filter.user && store.currentUser) {
      return this.state.filter.user === store.currentUser.email;
    }
    return false;
  };

  changeOrderBy = orderBy => {
    this.setState({ orderBy: orderBy }, () => {
      this._fetchUploads();
    });
  };

  render() {
    return (
      <div>
        {store.hasPermission("upload.view_all_uploads") ? (
          <div className="tabs is-centered">
            <ul>
              <li className={!this._filterOnYourUploads() ? "is-active" : ""}>
                <Link to="/uploads" onClick={this.filterOnAll}>
                  All Uploads
                </Link>
              </li>
              <li className={this._filterOnYourUploads() ? "is-active" : ""}>
                <Link
                  to={`/uploads?user=${store.currentUser.email}`}
                  onClick={this.filterOnYours}
                >
                  Your Uploads
                </Link>
              </li>
              <li>
                <Link to="/uploads/files/">All Files</Link>
              </li>
              <li>
                <Link to="/uploads/upload">Upload Now</Link>
              </li>
            </ul>
          </div>
        ) : (
          <div className="tabs is-centered">
            <ul>
              <li className={!this.state.filter.user ? "is-active" : ""}>
                <Link to="/uploads/">All Uploads</Link>
              </li>
              <li>
                <Link to="/uploads/upload">Upload Now</Link>
              </li>
            </ul>
          </div>
        )}
        <ShowNewUploadsCount
          count={this.state.newUploadsCount}
          refreshing={this.state.refreshing}
          refresh={this._refreshUploads}
        />
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
        {this.state.uploads && (
          <DisplayUploads
            loading={this.state.loading}
            uploads={this.state.uploads}
            canViewAll={this.state.canViewAll}
            aggregates={this.state.aggregates}
            total={this.state.total}
            batchSize={this.state.batchSize}
            location={this.props.location}
            filter={this.state.filter}
            updateFilter={this.updateFilter}
            resetAndReload={this.resetAndReload}
            previousLatestUpload={this.previousLatestUpload}
            changeOrderBy={this.changeOrderBy}
            orderBy={this.state.orderBy}
          />
        )}
      </div>
    );
  }
}

export default Uploads;

class ShowNewUploadsCount extends React.PureComponent {
  refresh = event => {
    event.preventDefault();
    this.props.refresh();
  };
  render() {
    if (!this.props.count) {
      return null;
    }
    return (
      <p className="is-pulled-right">
        <Link
          to="/uploads"
          className="button is-small is-info"
          disabled={this.props.refreshing}
          onClick={this.refresh}
        >
          <span className="icon">
            <i
              className={
                this.props.refreshing
                  ? "fa fa-refresh fa-spin fa-3x fa-fw"
                  : "fa fa-refresh"
              }
            />
          </span>{" "}
          <span>
            {pluralize(
              this.props.count,
              "new upload available",
              "new uploads available"
            )}
          </span>
        </Link>
      </p>
    );
  }
}

class DisplayUploads extends React.PureComponent {
  componentDidMount() {
    this._updateFilterInputs(this.props.filter, this.props.canViewAll);
  }

  componentWillReceiveProps(nextProps) {
    this._updateFilterInputs(nextProps.filter, nextProps.canViewAll);
  }

  _updateFilterInputs = (filter, canViewAll) => {
    if (canViewAll) {
      this.refs.user.value = filter.user || "";
    }
    this.refs.size.value = filter.size || "";
    this.refs.created_at.value = filter.created_at || "";
    this.refs.completed_at.value = filter.completed_at || "";
  };

  submitForm = event => {
    event.preventDefault();
    let user = "";
    if (this.props.canViewAll) {
      user = this.refs.user.value.trim();
    }
    const size = this.refs.size.value.trim();
    const created_at = this.refs.created_at.value.trim();
    const completed_at = this.refs.completed_at.value.trim();
    this.props.updateFilter({
      page: 1,
      user,
      size,
      created_at,
      completed_at
    });
  };

  resetFilter = event => {
    if (this.props.canViewAll) {
      this.refs.user.value = "";
    }
    this.refs.size.value = "";
    this.refs.created_at.value = "";
    this.refs.completed_at.value = "";
    this.props.resetAndReload(event);
  };

  isNew = date => {
    if (this.props.previousLatestUpload) {
      return date > this.props.previousLatestUpload;
    }
    return false;
  };

  render() {
    const { loading, uploads, aggregates } = this.props;

    const todayStr = format(new Date(), "yyyy-MM-dd");
    const todayFullStr = format(new Date(), "yyyy-MM-ddTHH:MM.SSSZ");
    return (
      <form onSubmit={this.submitForm}>
        <table className="table is-fullwidth">
          <thead>
            <tr>
              <th>Files</th>
              <th>User</th>
              <th>
                Size
                <SortLink
                  name="size"
                  current={this.props.orderBy}
                  onChangeSort={this.props.changeOrderBy}
                />
              </th>
              <th>
                Uploaded
                <SortLink
                  name="created_at"
                  title="Uploaded"
                  current={this.props.orderBy}
                  onChangeSort={this.props.changeOrderBy}
                />
              </th>
              <th>Completed</th>
            </tr>
          </thead>
          <tfoot>
            <tr>
              <td className="buttons">
                <button type="submit" className="button is-primary">
                  Filter Uploads
                </button>
                <button
                  type="button"
                  onClick={this.resetFilter}
                  className="button"
                >
                  Reset Filter
                </button>
              </td>
              <td>
                {this.props.canViewAll && (
                  <input
                    type="text"
                    className="input"
                    ref="user"
                    placeholder="filter..."
                  />
                )}
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
                  ref="created_at"
                  placeholder="filter..."
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="completed_at"
                  placeholder="filter..."
                />
              </td>
            </tr>
          </tfoot>
          <tbody>
            {!loading &&
              uploads.map(upload => (
                <tr key={upload.id}>
                  <td>
                    <Link
                      to={`/uploads/upload/${upload.id}`}
                      title="Click to see detailed information about all uploads"
                    >
                      {DisplayFilesSummary(
                        upload.files_count,
                        upload.files_incomplete_count,
                        upload.skipped_keys.length,
                        upload.ignored_keys.length
                      )}
                    </Link>{" "}
                    {upload.try_symbols ? (
                      <span
                        className="tag is-info"
                        title="Uploads for a Try build"
                      >
                        Try
                      </span>
                    ) : null}
                  </td>
                  <td>{upload.user.email}</td>
                  <td>{formatFileSize(upload.size)}</td>
                  <td>
                    <DisplayDate date={upload.created_at} />{" "}
                    {this.isNew(upload.created_at) && (
                      <span className="tag is-light">new</span>
                    )}
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

        <ExamplesOfFiltering todayStr={todayStr} todayFullStr={todayFullStr} />
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
          <b>User:</b> <code>@mozilla.com</code> to filter on any upload whose
          email contains this domain.
        </li>
        <li>
          <b>User:</b> <code>!peterbe@example.com</code> to filter on any upload
          whose email does NOT match that email.
        </li>
        <li>
          <b>Size:</b> <code>&gt;1mb</code> to filter all uploads <i>bigger</i>{" "}
          than one megabyte.
        </li>
        <li>
          <b>Uploaded:</b> <code>{todayStr}</code> to filter all uploads
          uploaded any time during this day (in UTC).
        </li>
        <li>
          <b>Uploaded:</b>{" "}
          <code>
            &gt;=
            {todayFullStr}
          </code>{" "}
          to filter all uploads uploaded after this ISO date (in UTC).
        </li>
        <li>
          <b>Uploaded:</b> <code>today</code> (or <code>yesterday</code>) to
          filter all uploads uploaded after yesterday's UTC daybreak.
        </li>
        <li>
          <b>Completed:</b> <code>incomplete</code> to filter all incomplete
          uploads.
        </li>
      </ul>
    </div>
  </article>
);

const ShowAggregates = ({ aggregates }) => {
  return (
    <nav className="level" style={{ marginTop: 60 }}>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Uploads</p>
          <p className="title">
            {aggregates.uploads.count
              ? thousandFormat(aggregates.uploads.count)
              : "n/a"}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Upload Sizes Sum</p>
          <p className="title">
            {aggregates.uploads.size.sum
              ? formatFileSize(aggregates.uploads.size.sum)
              : "n/a"}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Upload Sizes Avg</p>
          <p className="title">
            {aggregates.uploads.size.average
              ? formatFileSize(aggregates.uploads.size.average)
              : "n/a"}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p
            className="heading"
            title="Files with the uploads we know we can skip"
          >
            Sum Skipped Files
          </p>
          <p className="title">
            {aggregates.uploads.skipped.sum
              ? thousandFormat(aggregates.uploads.skipped.sum)
              : "n/a"}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading" title="Files we definitely uploaded">
            Sum Uploaded Files
          </p>
          <p className="title">
            {aggregates.files.count
              ? thousandFormat(aggregates.files.count)
              : "n/a"}
          </p>
        </div>
      </div>
    </nav>
  );
};
