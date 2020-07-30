/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */
import React from "react";
import { observer } from "mobx-react";
import { Loading, thousandFormat } from "./Common";
import { CopyToClipboard } from "react-copy-to-clipboard";
import Fetch from "./Fetch";
import store from "./Store";

const Symbolication = observer(
  class Symbolication extends React.Component {
    pageTitle = "Symbolication";
    componentDidMount() {
      document.title = this.pageTitle;
    }
    render() {
      return (
        <div className="content">
          <h1 className="title">{this.pageTitle}</h1>

          <p>
            Symbolication is when you send names of symbol file and stacks that
            refer to addresses. What you get back is the stack addresses
            converted to information from within the symbol file. In particular
            you get the code signature at that address.
          </p>
          <p>
            Symbolication is best done with tooling such as <code>curl</code>
            or Python <code>requests.post(…)</code>. This application here is to
            help you understand the API and sample it.
          </p>
          <Form />
          {store.currentUser && <Stats />}
        </div>
      );
    }
  }
);

export default Symbolication;

class Form extends React.PureComponent {
  state = {
    loading: false,
    jobs: [],
    result: null,
    jobInputs: 1,
    jsonBody: null,
    validationError: null,
  };

  submit = (event) => {
    event.preventDefault();
    if (!this.state.jobs.length) {
      alert("No jobs yet.");
    } else {
      const jsonBody = JSON.stringify({ jobs: this.state.jobs });
      this.setState({
        loading: true,
        jsonBody,
        result: null,
        validationError: null,
      });
      return fetch("/symbolicate/v5", {
        method: "POST",
        body: jsonBody,
        headers: new Headers({
          "Content-Type": "application/json",
        }),
      }).then((r) => {
        if (r.status === 200) {
          this.setState({ loading: false, validationError: null });
          r.json().then((response) => {
            this.setState({ result: response }, () => {
              const el = document.querySelector("div.showresult");
              if (el) {
                el.scrollIntoView();
              }
              if (store.fetchError) {
                store.fetchError = null;
              }
            });
          });
        } else if (r.status === 400) {
          r.json().then((data) => {
            this.setState(
              { validationError: data.error, loading: false },
              () => {
                const el = document.querySelector("div.validationerror");
                if (el) {
                  el.scrollIntoView();
                }
                if (store.fetchError) {
                  store.fetchError = null;
                }
              }
            );
          });
        } else {
          this.setState({ loading: false, validationError: null });
          store.fetchError = r;
        }
      });
    }
  };

  updateJob = (index, memoryMaps, stacks) => {
    const jobs = [...this.state.jobs];
    const maps = memoryMaps.map((mm) => mm.split(/\//));
    jobs[index] = { memoryMap: maps, stacks: [stacks] };
    this.setState({ jobs: jobs });
  };

  clear = (event) => {
    console.error("Not implemented yet");
  };

  render() {
    return (
      <div>
        {Array(this.state.jobInputs)
          .fill()
          .map((_, i) => {
            return (
              <JobForm
                key={i}
                updateJob={(mm, stacks) => this.updateJob(i, mm, stacks)}
              />
            );
          })}
        <div className="field is-grouped is-grouped-centered">
          <p className="control">
            <button
              className="button is-primary"
              onClick={this.submit}
              disabled={!this.state.jobs.length}
            >
              Symbolicate!
            </button>
          </p>
          <p className="control">
            <button
              type="button"
              className="button is-light"
              onClick={this.clear}
            >
              Clear
            </button>
          </p>
        </div>
        {this.state.loading ? <Loading /> : null}
        {this.state.jsonBody ? (
          <PreviewJSONBody json={this.state.jsonBody} />
        ) : null}
        {this.state.validationError ? (
          <ShowValidationError error={this.state.validationError} />
        ) : null}
        {this.state.result ? <ShowResult result={this.state.result} /> : null}
        {this.state.result && this.state.jsonBody ? (
          <ShowCurl json={this.state.jsonBody} />
        ) : null}
      </div>
    );
  }
}

class CopyToClipboardPureComponent extends React.PureComponent {
  state = { copied: false };

  componentWillUnmount() {
    this.dismounted = true;
  }

  setCopied = (truth = true) => {
    this.setState({ copied: truth });
  };

  componentDidUpdate() {
    if (this.state.copied) {
      window.setTimeout(() => {
        if (!this.dismounted) {
          this.setCopied(false);
        }
      }, 3000);
    }
  }
}

class PreviewJSONBody extends CopyToClipboardPureComponent {
  render() {
    const json = JSON.stringify(JSON.parse(this.props.json), undefined, 2);
    return (
      <div className="box">
        <h4>JSON We're Sending</h4>
        <pre>{json}</pre>
        <CopyToClipboard text={json} onCopy={this.setCopied}>
          <button type="button" className="button">
            Copy to clipboard
          </button>
        </CopyToClipboard>
        {this.state.copied && <small> Copied!</small>}
      </div>
    );
  }
}

class ShowValidationError extends React.PureComponent {
  render() {
    const { error } = this.props;
    return (
      <article className="message is-danger validationerror">
        <div className="message-header">
          <p>Validation Error</p>
        </div>
        <div className="message-body">
          <code>{error}</code>
        </div>
      </article>
    );
  }
}

class ShowResult extends CopyToClipboardPureComponent {
  render() {
    const json = JSON.stringify(this.props.result, undefined, 2);
    return (
      <div className="box showresult">
        <h3>RESULT</h3>
        <pre>{json}</pre>

        <CopyToClipboard text={json} onCopy={this.setCopied}>
          <button type="button" className="button">
            Copy to clipboard
          </button>
        </CopyToClipboard>
        {this.state.copied && <small> Copied!</small>}
      </div>
    );
  }
}

class ShowCurl extends CopyToClipboardPureComponent {
  render() {
    const { json } = this.props;
    const protocol = window.location.protocol;
    const hostname = window.location.host.replace(
      "localhost:3000",
      "localhost:8000"
    );
    const absoluteUrl = `${protocol}//${hostname}/symbolicate/v5`;
    const command = `curl -XPOST -d '${json}' ${absoluteUrl}`;
    return (
      <div className="box">
        <h3>
          <code>curl</code> Command
        </h3>
        <pre>{command}</pre>
        <CopyToClipboard text={command} onCopy={this.setCopied}>
          <button type="button" className="button">
            Copy to clipboard
          </button>
        </CopyToClipboard>
        {this.state.copied && <small> Copied!</small>}
      </div>
    );
  }
}

class JobForm extends React.PureComponent {
  state = {
    memoryMaps: [],
    stacksInputs: 1,
    invalidMemoryMaps: [],
    defaultMemoryMap: 0,
    stacks: [],
  };
  componentDidMount() {
    if (this.refs.memoryMap.value) {
      this.updateMemoryMap();
    }
  }
  updateMemoryMap = () => {
    const lines = this.refs.memoryMap.value
      .trim()
      .split(/\n/g)
      .filter((line) => line.trim())
      .map((line) => line.trim());
    const valid = new Set();
    const invalid = new Set();
    lines.forEach((line) => {
      let pathname = line;
      try {
        const split = new URL(line).pathname.split(/\//g);
        pathname = [split[1], split[2]].join("/");
      } catch (_) {}
      if (pathname.split(/\//g).length === 2) {
        valid.add(pathname);
      } else {
        invalid.add(line);
      }
    });
    if (invalid.size) {
      this.setState({ invalidMemoryMaps: Array.from(invalid), memoryMaps: [] });
    } else {
      this.setState(
        { memoryMaps: Array.from(valid), invalidMemoryMaps: [] },
        () => {
          this.refs.memoryMap.value = this.state.memoryMaps.join("\n");
          // console.log("NEW VALUE:", { value: this.refs.memoryMap.value });
        }
      );
    }
  };

  SESSION_STORAGE_MEMORYMAPS_KEY = "memoryMapValue";

  render() {
    const placeholder = `
E.g. https://symbols.mozilla.org/GenerateOCSPResponse.pdb/3AACAD4A42BD449B953B5222B3CEB7233/GenerateOCSPResponse.sym
or
GenerateOCSPResponse.pdb/3AACAD4A42BD449B953B5222B3CEB7233
    `.trim();

    const defaultDefaultValue = `
    GenerateOCSPResponse.pdb/3AACAD4A42BD449B953B5222B3CEB7233
https://symbols.mozilla.org/AccessibleMarshal.pdb/3D2A1F8439554FBF8A0E0F24BEF8F0F52/AccessibleMarshal.sym

  `.trim();
    const defaultValue =
      window.sessionStorage.getItem(this.SESSION_STORAGE_MEMORYMAPS_KEY) ||
      defaultDefaultValue;

    return (
      <div>
        <div className="field">
          <label className="label">Symbols</label>
          <div className="control">
            <textarea
              className="textarea"
              ref="memoryMap"
              placeholder={placeholder}
              defaultValue={defaultValue}
              onBlur={(event) => {
                this.updateMemoryMap();
              }}
            />
          </div>
          {this.state.invalidMemoryMaps.length ? (
            <p className="help is-danger">
              {this.state.invalidMemoryMaps.length} invalid lines:{" "}
              {this.state.invalidMemoryMaps.map((x) => (
                <code key={x}>{x}</code>
              ))}
            </p>
          ) : null}
        </div>

        <label className="label">Stacks</label>
        {Array(this.state.stacksInputs)
          .fill()
          .map((_, i) => {
            return (
              <StackForm
                key={i}
                memoryMaps={this.state.memoryMaps}
                defaultMemoryMap={this.state.defaultMemoryMap}
                isNext={i === this.state.stacksInputs - 1}
                addStackInput={(address, memoryMap) => {
                  this.setState(
                    {
                      stacks: [...this.state.stacks, [memoryMap, address]],
                      stacksInputs: this.state.stacksInputs + 1,
                      defaultMemoryMap: memoryMap,
                    },
                    () => {
                      this.props.updateJob(
                        this.state.memoryMaps,
                        this.state.stacks
                      );
                      if (this.state.memoryMaps.length) {
                        const memoryMapsString = this.state.memoryMaps.join(
                          "\n"
                        );
                        if (memoryMapsString !== defaultDefaultValue) {
                          window.sessionStorage.setItem(
                            this.SESSION_STORAGE_MEMORYMAPS_KEY,
                            memoryMapsString
                          );
                        }
                      }
                    }
                  );
                }}
              />
            );
          })}
      </div>
    );
  }
}

class StackForm extends React.PureComponent {
  state = {
    invalidAddress: false,
  };
  add = (event) => {
    event.preventDefault();
    const address = parseInt(this.refs.address.value, 10);
    if (isNaN(address)) {
      this.setState({ invalidAddress: true });
    } else {
      this.setState({ invalidAddress: false }, () => {
        this.props.addStackInput(
          address,
          parseInt(this.refs.memoryMap.value, 10)
        );
      });
    }
  };
  componentDidMount() {
    if (this.props.isNext) {
      this.refs.address.focus();
    }
  }
  render() {
    return (
      <form onSubmit={this.add}>
        <div className="field has-addons has-addons-centered">
          <p className="control">
            <span className="select">
              <select
                ref="memoryMap"
                defaultValue={this.props.defaultMemoryMap}
              >
                {this.props.memoryMaps.map((memoryMap, i) => {
                  return (
                    <option value={i} key={memoryMap}>
                      {i}. {memoryMap}
                    </option>
                  );
                })}
              </select>
            </span>
          </p>
          <div className="control is-expanded">
            <input className="input" ref="address" type="text" />
            {this.state.invalidAddress ? (
              <p className="help is-danger">
                Not a valid address (must be an integer)
              </p>
            ) : null}
          </div>
          <p className="control">
            <button type="submit" className="button">
              Add
            </button>
          </p>
        </div>
      </form>
    );
  }
}

class Stats extends React.PureComponent {
  state = {
    loading: true,
    stats: null,
  };

  async componentDidMount() {
    // Note! This endpoint requires that the user is logged in.
    const response = await Fetch("/api/stats/symbolication");
    this.setState({ loading: false });
    if (response.ok) {
      if (store.fetchError) {
        store.fetchError = null;
      }
      const data = await response.json();
      this.setState({
        stats: data.symbolications,
      });
    } else {
      store.fetchError = response;
    }
  }

  render() {
    return (
      <div style={{ marginTop: 40 }}>
        <h2 className="title">Symbolication Stats</h2>
        {this.state.loading ? <Loading /> : null}

        {this.state.stats && <StatsTable data={this.state.stats} />}
      </div>
    );
  }
}

class StatsTable extends React.PureComponent {
  render() {
    const { data } = this.props;
    return (
      <table className="table">
        <thead>
          <tr>
            <th />
            <th>v5</th>
            <th>
              v4 <small>(legacy)</small>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Today</th>
            <td>{thousandFormat(data.v5.today)}</td>
            <td>{thousandFormat(data.v4.today)}</td>
          </tr>
          <tr>
            <th>Yesterday</th>
            <td>{thousandFormat(data.v5.yesterday)}</td>
            <td>{thousandFormat(data.v4.yesterday)}</td>
          </tr>
        </tbody>
      </table>
    );
  }
}
