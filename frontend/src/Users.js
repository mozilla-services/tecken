import React, { PureComponent } from "react";
import { Link } from "react-router-dom";

import { Loading, DisplayDate } from "./Common";
import Fetch from "./Fetch";
import store from "./Store";

class Users extends PureComponent {
  constructor(props) {
    super(props);
    this.pageTitle = "User Management";
    this.state = {
      loading: true,
      users: null,
      displayUsers: null,
      showInactiveUsers: false,
    };
  }
  componentWillMount() {
    store.resetApiRequests();
  }

  componentDidMount() {
    document.title = this.pageTitle;
    this._fetchUsers();
  }

  _fetchUsers = () => {
    this.setState({ loading: true });
    Fetch("/api/_users/", { credentials: "same-origin" }).then((r) => {
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
        return r.json().then((response) => {
          this.setState({
            users: response.users,
            displayUsers: this.state.showInactiveUsers
              ? response.users
              : this._filterInActiveUsers(response.users),
            loading: false,
          });
        });
      } else {
        store.fetchError = r;
      }
    });
  };

  _filterInActiveUsers = (users) => {
    return users.filter((user) => {
      if (!user.is_active) {
        return false;
      }
      if (!user.last_login) {
        return false;
      }
      return true;
    });
  };

  render() {
    return (
      <div>
        <h1 className="title">{this.pageTitle}</h1>
        {this.state.loading ? (
          <Loading />
        ) : (
          <ShowActiveUsersToggle
            on={this.state.showInactiveUsers}
            change={() => {
              this.setState(
                {
                  showInactiveUsers: !this.state.showInactiveUsers,
                },
                () => {
                  this.setState({
                    displayUsers: this.state.showInactiveUsers
                      ? this.state.users
                      : this._filterInActiveUsers(this.state.users),
                  });
                }
              );
            }}
          />
        )}
        {this.state.displayUsers !== null ? (
          <DisplayUsers users={this.state.displayUsers} />
        ) : null}
      </div>
    );
  }
}

export default Users;

class ShowActiveUsersToggle extends React.PureComponent {
  render() {
    return (
      <p>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={this.props.on}
            onChange={this.props.change}
          />{" "}
          Show inactive users
        </label>
      </p>
    );
  }
}

class DisplayUsers extends PureComponent {
  state = {
    filter: {
      q: "",
    },
  };

  onEdit = (event, id) => {
    event.preventDefault();
    this.props.editUser(id);
  };

  _resetFilter = (event) => {
    event.preventDefault();
    this.setState({
      filter: {
        q: "",
      },
    });
  };

  render() {
    const { users } = this.props;
    if (!users) {
      return (
        <p>
          There are <b>no users</b>.
        </p>
      );
    }
    return (
      <table className="table is-fullwidth">
        <thead>
          <tr>
            <th>Email</th>
            <th>Last Login</th>
            <th>Permissions</th>
            <th>Uploads</th>
            <th>API Tokens</th>
            <th />
          </tr>
        </thead>
        <tfoot>
          <tr>
            <th>
              <input
                type="search"
                className="input"
                value={this.state.filter.q}
                onChange={(e) =>
                  this.setState({ filter: { q: e.target.value } })
                }
                placeholder="Filter by email"
              />
            </th>
            <th />
            <th />
            <th />
            <th />
            <th>
              {this.state.filter.q && (
                <button
                  className="button is-primary"
                  onClick={this._resetFilter}
                >
                  Clear filter
                </button>
              )}
            </th>
          </tr>
        </tfoot>
        <tbody>
          {users.map((user) => {
            // Yeah, it's a unscalable hack to filter in render().
            // It's also not scalable to load ALL users into memory with AJAX.
            // There's not even pagination.
            if (this.state.filter.q) {
              // return null if the email doesn't match
              if (
                !user.email
                  .toLowerCase()
                  .includes(this.state.filter.q.toLowerCase())
              ) {
                return null;
              }
            }
            return (
              <tr key={user.id}>
                <td>
                  {user.email}{" "}
                  {!user.is_active ? (
                    <span className="tag is-danger">Not Active</span>
                  ) : null}
                </td>
                <td>
                  {user.last_login ? (
                    <DisplayDate date={user.last_login} />
                  ) : (
                    <i>never logged in</i>
                  )}{" "}
                  <small>
                    (joined <DisplayDate date={user.date_joined} />)
                  </small>
                </td>
                <td>
                  {user.is_superuser ? (
                    <span className="tag is-warning">Superuser</span>
                  ) : (
                    user.permissions.map((p) => (
                      <code key={p.id} style={{ display: "block" }}>
                        {p.name}
                      </code>
                    ))
                  )}
                </td>
                <td>{user.no_uploads}</td>
                <td>{user.no_tokens}</td>
                <td>
                  <Link to={`/users/${user.id}`} className="button is-info">
                    Edit
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }
}
