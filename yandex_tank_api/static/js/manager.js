(function() {
  var app;

  app = angular.module("ng-tank-manager", ['ui.ace']);

  app.controller("TankManager", function($scope, $interval, $http) {
    var runTest, updateStatus;
    updateStatus = function() {
      return $http.get("status").success(function(data) {
        return $scope.status = data;
      });
    };
    runTest = function() {
      return $http.post("run", $scope.tankConfig).success(function(data) {
        $scope.reply = data;
        return console.log(data);
      });
    };
    return $interval(updateStatus, 1000);
  });

}).call(this);
