import React from "react";
import { Link } from "react-router-dom";
import Fetch from "./Fetch";
import store from "./Store";

import {
  Loading,
  Pagination,
  TableSubTitle,
  DisplayDate,
  thousandFormat,
  ShowValidationErrors,
  filterToQueryString,
  parseQueryString,
  SortLink,
} from "./Common";

class DownloadsMissing extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      pageTitle: "Downloads Missing",
      loading: true,
      missing: null,
      aggregates: null,
      total: null,
      batchSize: null,
      apiUrl: null,
      filter: {},
      validationErrors: null,
      orderBy: null,
    };
  }

  componentDidMount() {
    document.title = this.state.pageTitle;
    store.resetApiRequests();

    if (this.props.location.search) {
      this.setState(
        { filter: parseQueryString(this.props.location.search) },
        () => {
          this._fetchMissing();
        }
      );
    } else {
      this._fetchMissing();
    }
  }

  _fetchMissing = () => {
    // If the backend is pretty fast, the new XHR content comes in
    // quickly and it's quite distracting to have to switch on the
    // loading animation just to, almost immediately, switch off
    // and display the new data.
    this.setLoadingTimer = window.setTimeout(() => {
      if (!this.dismounted) {
        this.setState({ loading: true });
      }
    }, 1000);
    let url = "/api/downloads/missing/";
    const qs = filterToQueryString(this.state.filter, this.state.orderBy);
    if (qs) {
      url += "?" + qs;
    }
    this.props.history.push({ search: qs });

    return Fetch(url, {}).then((r) => {
      if (this.setLoadingTimer) {
        window.clearTimeout(this.setLoadingTimer);
      }
      this.setState({ loading: false });
      if (r.status === 200) {
        if (store.fetchError) {
          store.fetchError = null;
        }
        return r.json().then((response) => {
          this.setState({
            missing: response.missing,
            aggregates: response.aggregates,
            total: response.total,
            batchSize: response.batch_size,
            validationErrors: null,
            orderBy: response.order_by,
          });
        });
      } else if (r.status === 400) {
        return r.json().then((data) => {
          this.setState({
            loading: false,
            refreshing: false,
            validationErrors: data.errors,
          });
        });
      } else {
        store.fetchError = r;
        // Always return a promise
        return Promise.resolve();
      }
    });
  };

  updateFilter = (newFilters) => {
    this.setState(
      {
        filter: Object.assign({}, this.state.filter, newFilters),
      },
      this._fetchMissing
    );
  };

  resetAndReload = (event) => {
    event.preventDefault();
    this.setState({ filter: {}, validationErrors: null }, () => {
      this._fetchMissing();
    });
  };

  changeOrderBy = (orderBy) => {
    this.setState({ orderBy: orderBy }, () => {
      this._fetchMissing();
    });
  };

  render() {
    return (
      <div>
        <div className="tabs is-centered">
          <ul>
            <li className="is-active">
              <Link to="/downloads/missing">Downloads Missing</Link>
            </li>
            <li>
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

        {this.state.missing && (
          <DisplayMissingSymbols
            missing={this.state.missing}
            aggregates={this.state.aggregates}
            total={this.state.total}
            batchSize={this.state.batchSize}
            location={this.props.location}
            filter={this.state.filter}
            updateFilter={this.updateFilter}
            resetAndReload={this.resetAndReload}
            changeOrderBy={this.changeOrderBy}
            orderBy={this.state.orderBy}
          />
        )}
      </div>
    );
  }
}

export default DownloadsMissing;

class DisplayMissingSymbols extends React.PureComponent {
  componentDidMount() {
    this._updateFilterInputs(this.props.filter);
  }

  componentWillReceiveProps(nextProps) {
    this._updateFilterInputs(nextProps.filter);
  }

  _updateFilterInputs = (filter) => {
    this.refs.modified_at.value = filter.modified_at || "";
    this.refs.count.value = filter.count || "";
    this.refs.symbol.value = filter.symbol || "";
    this.refs.debugid.value = filter.debugid || "";
    this.refs.filename.value = filter.filename || "";
  };

  submitForm = (event) => {
    event.preventDefault();
    const modified_at = this.refs.modified_at.value.trim();
    const count = this.refs.count.value.trim();
    const symbol = this.refs.symbol.value.trim();
    const debugid = this.refs.debugid.value.trim();
    const filename = this.refs.filename.value.trim();
    this.props.updateFilter({
      page: 1,
      modified_at,
      count,
      symbol,
      debugid,
      filename,
    });
  };

  resetFilter = (event) => {
    this.refs.symbol.value = "";
    this.refs.debugid.value = "";
    this.refs.filename.value = "";
    this.refs.count.value = "";
    this.refs.modified_at.value = "";
    this.props.resetAndReload(event);
  };

  render() {
    const { missing, aggregates } = this.props;

    return (
      <form onSubmit={this.submitForm}>
        <table className="table files-table is-fullwidth">
          <thead>
            <tr>
              <th>
                Symbol/DebugID/Filename
                <br />
                CodeFile/CodeID
              </th>
              <th title="A missing symbol is only counted once per every 24 hours">
                Count
                <SortLink
                  name="count"
                  current={this.props.orderBy}
                  onChangeSort={this.props.changeOrderBy}
                />
              </th>
              <th>
                Updated
                <SortLink
                  name="modified_at"
                  title="Updated"
                  current={this.props.orderBy}
                  onChangeSort={this.props.changeOrderBy}
                />
              </th>
              <th>
                First Seen
                <SortLink
                  name="created_at"
                  title="First Seen"
                  current={this.props.orderBy}
                  onChangeSort={this.props.changeOrderBy}
                />
              </th>
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
                  style={{ width: "30%" }}
                />{" "}
                <input
                  type="text"
                  className="input"
                  ref="debugid"
                  placeholder="debugid..."
                  style={{ width: "30%" }}
                />{" "}
                <input
                  type="text"
                  className="input"
                  ref="filename"
                  placeholder="filename..."
                  style={{ width: "30%" }}
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="count"
                  placeholder="filter..."
                  style={{ width: 100 }}
                />
              </td>
              <td>
                <input
                  type="text"
                  className="input"
                  ref="modified_at"
                  placeholder="filter..."
                />
              </td>
              <td className="buttons">
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
            {missing.map((missing) => (
              <tr key={missing.id}>
                <td className="file-key">
                  {missing.symbol}/{missing.debugid}/{missing.filename}
                  <br />
                  {missing.code_file || missing.code_id ? (
                    <ShowMissingCodeAndId
                      file={missing.code_file}
                      id={missing.code_id}
                    />
                  ) : null}
                </td>
                <td>{missing.count}</td>
                <td>
                  <DisplayDate date={missing.modified_at} />
                </td>
                <td>
                  <DisplayDate date={missing.created_at} />
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
    );
  }
}

const ShowMissingCodeAndId = ({ file, id }) => {
  if (file && id) {
    return (
      <span>
        <b>file:</b> {file}
        {"   "}
        <b>id:</b> {id}
      </span>
    );
  } else if (file) {
    return (
      <span>
        <b>file:</b> {file}
      </span>
    );
  } else if (id) {
    return (
      <span>
        <b>id:</b> {file}
      </span>
    );
  }
};

const ShowAggregates = ({ aggregates }) => {
  return (
    <nav className="level" style={{ marginTop: 60 }}>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Total</p>
          <p className="title">{thousandFormat(aggregates.missing.total)}</p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Last 1 Day</p>
          <p className="title">
            {thousandFormat(aggregates.missing.last_1_days)}
          </p>
        </div>
      </div>
      <div className="level-item has-text-centered">
        <div>
          <p className="heading">Last 30 Days</p>
          <p className="title">
            {thousandFormat(aggregates.missing.last_30_days)}
          </p>
        </div>
      </div>
    </nav>
  );
};
