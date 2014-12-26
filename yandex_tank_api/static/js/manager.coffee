app = angular.module("ng-tank-manager", ['ui.ace'])

app.controller "TankManager", ($scope, $interval, $http) ->
  updateStatus = () ->
    $http.get("status").success (data) ->
      $scope.status = data

  $scope.runTest = () ->
    $http.post("run", $scope.tankConfig).success (data) ->
      $scope.reply = data
      console.log(data)

  $interval(updateStatus, 1000)
