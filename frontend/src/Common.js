/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */
import React from "react";
import FontAwesome from "react-fontawesome";
import "font-awesome/css/font-awesome.css";
import { Link } from "react-router-dom";

import {
  toDate,
  isBefore,
  formatDistance,
  formatDistanceStrict,
  differenceInSeconds,
  differenceInMilliseconds,
} from "date-fns";
import parseISO from "date-fns/parseISO";

// Big number signifying we don't know what the count is. This needs to match
// the BIG_NUMBER API total value.
const BIG_NUMBER = 1000000;

export function parseISODate(input) {
  return toDate(parseISO(input));
}

export const Loading = () => (
  <p className="has-text-centered">
    <span className="icon is-large">
      <FontAwesome name="cog" spin size="5x" />
      <span className="sr-only">Loading...</span>
    </span>
  </p>
);

export const DisplayDate = ({ date }) => {
  if (date === null) {
    throw new Error("date is null");
  }
  const dateObj = parseISODate(date);
  const now = new Date();
  if (isBefore(dateObj, now)) {
    return <span title={date}>{formatDistance(dateObj, now)} ago</span>;
  } else {
    return <span title={date}>in {formatDistance(dateObj, now)}</span>;
  }
};

export const DisplayDateDifference = ({ from, to, suffix = "" }) => {
  const fromObj = parseISODate(from);
  const toObj = parseISODate(to);
  const secDiff = differenceInSeconds(toObj, fromObj);
  if (secDiff === 0) {
    const msecDiff = differenceInMilliseconds(toObj, fromObj);
    if (msecDiff > 0) {
      return (
        <span title={`From ${fromObj} to ${toObj}`}>
          {msecDiff} ms
          {suffix && ` ${suffix}`}
        </span>
      );
    }
  }
  return (
    <span title={`From ${fromObj} to ${toObj}`}>
      {formatDistanceStrict(fromObj, toObj)}
      {suffix && ` ${suffix}`}
    </span>
  );
};

export const thousandFormat = (x) => {
  return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
};

export const formatFileSize = (bytes, decimals = 0) => {
  if (!bytes) return "0 bytes";
  var k = 1024;
  var dm = decimals + 1 || 3;
  var sizes = ["bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
  var i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
};

export const formatSeconds = (seconds) => {
  if (seconds < 1) {
    // milliseconds
    return (seconds * 1000).toFixed(0) + "ms";
  } else if (seconds > 3000) {
    return (seconds / 60).toFixed(1) + "m";
  } else if (seconds < 60) {
    return seconds.toFixed(1) + "s";
  } else {
    const minutes = Math.floor(seconds / 60);
    seconds = Math.round(seconds % 60);
    return `${minutes}m${seconds}s`;
  }
};
export const BooleanIcon = (bool) => (
  <span className="icon" style={{ color: bool ? "green" : "red" }}>
    <i className={bool ? "fa fa-check" : "fa fa-close"} />
  </span>
);

export const Pagination = ({
  location,
  total,
  batchSize,
  currentPage,
  updateFilter,
  hasNext,
}) => {
  if (!currentPage) {
    currentPage = 1;
  } else if (typeof currentPage === "string") {
    currentPage = parseInt(currentPage, 10);
  }

  const nextPageUrl = (page) => {
    const searchParams = new URLSearchParams(location.search);
    searchParams.set("page", page);
    return location.pathname + "?" + searchParams.toString();
  };

  const goTo = (event, page) => {
    event.preventDefault();
    updateFilter({ page });
  };

  const hasPrevPage = (currPage) => {
    // in /uploads/files 'total' is loaded async so there's no guarantee it'll be present
    if (total !== undefined) {
      return currPage - 1 >= 1 && (currPage - 2) * batchSize < total;
    } else {
      return currPage - 1 >= 1;
    }
  };

  const hasNextPage = (currPage) => {
    if (hasNext !== undefined) {
      return hasNext;
    } else {
      return currPage + 1 >= 1 && currPage * batchSize < total;
    }
  };

  return (
    <nav className="pagination is-centered">
      <Link
        className="pagination-previous"
        to={nextPageUrl(currentPage - 1)}
        onClick={(e) => hasPrevPage(currentPage) && goTo(e, currentPage - 1)}
        disabled={!hasPrevPage(currentPage)}
      >
        Previous
      </Link>
      <ul className="pagination-list">
        <li>Page {currentPage}</li>
      </ul>
      <Link
        to={nextPageUrl(currentPage + 1)}
        className="pagination-next"
        onClick={(e) => hasNextPage(currentPage) && goTo(e, currentPage + 1)}
        disabled={!hasNextPage(currentPage)}
      >
        Next page
      </Link>
    </nav>
  );
};

export const TableSubTitle = ({
  total,
  page,
  batchSize,
  calculating = false,
}) => {
  if (total === null || calculating) {
    return null;
  }
  page = page || 1;
  var totalText = "";
  var totalPagesText = "";
  if (total === BIG_NUMBER) {
    totalText = "Lots";
    totalPagesText = "many";
  } else {
    totalText = thousandFormat(total);
    totalPagesText = thousandFormat(Math.ceil(total / batchSize));
  }
  if (calculating) {
    return <h2 className="subtitle">Calculating ...</h2>;
  } else {
    return (
      <h2 className="subtitle">
        {totalText} Found (Page {thousandFormat(page)} of {totalPagesText})
      </h2>
    );
  }
};

export const FilterSummary = ({ filter }) => {
  const filterParts = [];
  for (const [key, value] of Object.entries(filter)) {
    if (key != "page" && value != "") {
      filterParts.push(`${key}: ${value}`);
    }
  }
  const filterValue = filterParts.join(", ");
  return <span>{filterValue}</span>;
};

export const pluralize = (number, singular, plural) => {
  if (number === 1) {
    return `1 ${singular}`;
  } else {
    return `${number} ${plural}`;
  }
};

export const DisplayFilesSummary = (files, incomplete, skipped, ignored) => {
  const sentences = [];
  sentences.push(pluralize(files, "file uploaded", "files uploaded"));
  if (incomplete) {
    // FIXME(willkg): If the upload is interrupted during processing, Tecken
    // only has records for files it started processing. All the files it
    // hadn't gotten to aren't accounted for in either the uploaded or
    // incomplete lists.
    sentences.push(
      pluralize(
        incomplete,
        "file incomplete (or more)",
        "files incomplete (or more)"
      )
    );
  }
  sentences.push(`${skipped} skipped`);
  // Currently ignoring the 'ignored'
  return sentences.join(". ") + ".";
};

export const ShowValidationErrors = ({ errors, resetAndReload }) => {
  return (
    <div className="notification is-danger">
      <button className="delete" onClick={resetAndReload} />
      <h4>Filter validation errors</h4>
      <ul>
        {Object.keys(errors).map((key) => {
          return (
            <li key={key}>
              <b>{key}</b> - <code>{errors[key]}</code>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export const parseQueryString = (qs) => {
  const searchParams = new URLSearchParams(qs);
  const parsed = {};
  for (let [key, value] of searchParams) {
    const already = parsed[key];
    if (already === undefined) {
      parsed[key] = value;
    } else if (Array.isArray(already)) {
      parsed[key].push(value);
    } else {
      parsed[key] = [already, value];
    }
  }
  return parsed;
};

export const filterToQueryString = (filterObj, overrides) => {
  const copy = Object.assign(overrides || {}, filterObj);
  const searchParams = new URLSearchParams();
  Object.entries(copy).forEach(([key, value]) => {
    if (Array.isArray(value) && value.length) {
      value.forEach((v) => searchParams.append(key, v));
    } else if (value) {
      searchParams.set(key, value);
    }
  });
  searchParams.sort();
  return searchParams.toString();
};

const URLTag = (url) => <span className="url">{url}</span>;

export const ShowUploadMetadata = ({ upload }) => {
  return (
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
          <td>{upload.try_symbols ? "Yes" : "No"}</td>
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
                  {upload.redirect_urls.map((url) => (
                    <li key={url}>{URLTag(url)}</li>
                  ))}
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
                {" "}
                (took{" "}
                <DisplayDateDifference
                  from={upload.created_at}
                  to={upload.completed_at}
                />
                )
              </small>
            ) : null}
          </td>
        </tr>
      </tbody>
    </table>
  );
};

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
              {" "}
              (took{" "}
              <DisplayDateDifference
                from={file.created_at}
                to={file.completed_at}
              />
              )
            </small>
          ) : null}
        </td>
      </tr>
    </tbody>
  </table>
);

export const ShowFileSymData = ({ file }) => (
  <table className="table is-fullwidth">
    <tbody>
      <tr>
        <th>Debug filename</th>
        <td>{file.debug_filename}</td>
      </tr>
      <tr>
        <th>Debug id</th>
        <td>{file.debug_id}</td>
      </tr>
      <tr>
        <th>Code file (Windows-only)</th>
        <td>{file.code_file}</td>
      </tr>
      <tr>
        <th>Code id (Windows-only)</th>
        <td>{file.code_id}</td>
      </tr>
      <tr>
        <th>Generator</th>
        <td>{file.generator}</td>
      </tr>
    </tbody>
  </table>
);

const capitalize = (s) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
};

export class SortLink extends React.PureComponent {
  change = (event) => {
    event.preventDefault();
    const { current, name } = this.props;
    let reverse = true;
    if (current && current.sort === name) {
      reverse = !current.reverse;
    }
    this.props.onChangeSort({
      sort: name,
      reverse: reverse,
    });
  };
  render() {
    const { current, name } = this.props;
    const title = this.props.title || capitalize(name);
    const currentUrl = document.location.pathname;
    let isCurrent = false;
    let isReverse = true;
    if (current && current.sort === name) {
      isCurrent = true;
      isReverse = current.reverse;
    }
    let arrow;
    if (isCurrent) {
      if (isReverse) {
        arrow = "⬇";
      } else {
        arrow = "⬆";
      }
    } else {
      arrow = "⇣";
    }
    return (
      <Link
        to={currentUrl}
        title={`Click to sort by ${title}`}
        onClick={this.change}
      >
        {arrow}
      </Link>
    );
  }
}
